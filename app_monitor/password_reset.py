import hashlib
import hmac
import ipaddress
import logging
import math
import secrets
import smtplib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import get_password_validators, validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import PasswordResetRequest as Reset, PasswordResetService


logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=5)
COOLDOWN = timedelta(seconds=60)
ONE_HOUR = timedelta(hours=1)
WORKER_TIMEOUT = timedelta(seconds=45)
MAX_ATTEMPTS = 5
ACCEPTED = '如果该邮箱已注册，验证码将发送至该邮箱。'
INVALID = '验证码错误、已过期或不可用，请检查后重试或重新获取。'
UNAVAILABLE = '验证码邮件服务暂时不可用，请稍后重试。'
DEFAULT_RESET_VALIDATORS = [
    {'NAME': f'django.contrib.auth.password_validation.{name}'}
    for name in ('UserAttributeSimilarityValidator', 'MinimumLengthValidator',
                 'CommonPasswordValidator', 'NumericPasswordValidator')
]


class EmailInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254, error_messages={'invalid': '请输入有效邮箱地址。'})

    def validate_email(self, value):
        return value.lower()


class ConfirmInput(EmailInput):
    code = serializers.RegexField(r'\A[0-9]{6}\Z', trim_whitespace=False,
                                  error_messages={'invalid': '请输入 6 位数字验证码。'})
    new_password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)
    confirm_password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': '两次输入的密码不一致。'})
        return attrs


def configured():
    return bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD and settings.DEFAULT_FROM_EMAIL
                and len(settings.PASSWORD_RESET_HMAC_KEY) >= 32)


def digest(*parts):
    message = '\0'.join(('ark-geoai/password-reset', *map(str, parts)))
    return hmac.new(settings.PASSWORD_RESET_HMAC_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def generate_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def client_ip(request):
    address = request.META.get('REMOTE_ADDR')
    if settings.PASSWORD_RESET_TRUST_PROXY and address in (None, '', '127.0.0.1', '::1'):
        address = request.META.get('HTTP_X_REAL_IP', address)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return 'unknown'
    return str(getattr(ip, 'ipv4_mapped', None) or ip)


def find_user(email, *, lock=False):
    users = get_user_model().objects.filter(email__iexact=email).order_by('pk')
    if lock:
        users = users.select_for_update()
    matches = list(users[:2])
    if len(matches) == 1 and matches[0].is_active and matches[0].has_usable_password():
        return matches[0]
    return None


def retry_after(query, now, window, limit):
    threshold = query.filter(created_at__gt=now - window).order_by('-created_at', '-pk')
    oldest = next(iter(threshold.values_list('created_at', flat=True)[limit - 1:limit]), None)
    return max(0, math.ceil((oldest + window - now).total_seconds())) if oldest else 0


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def send_code(request):
    form = EmailInput(data=request.data)
    form.is_valid(raise_exception=True)
    if not configured():
        return Response({'detail': UNAVAILABLE}, status=503)

    email = form.validated_data['email']
    email_key = digest('email', email)
    ip_key = digest('ip', client_ip(request))
    with transaction.atomic():
        # Serialize admissions across workers. SMTP runs separately and never holds this lock.
        service, _ = PasswordResetService.objects.select_for_update().get_or_create(pk=1)
        now = timezone.now()
        if (not service.worker_seen_at or now - service.worker_seen_at > WORKER_TIMEOUT
                or (service.unavailable_until and now < service.unavailable_until)):
            return Response({'detail': UNAVAILABLE}, status=503)
        requests = Reset.objects.all()
        by_email = requests.filter(email_key=email_key)
        wait = max(retry_after(by_email, now, COOLDOWN, 1),
                   retry_after(by_email, now, ONE_HOUR, 5),
                   retry_after(requests.filter(ip_key=ip_key), now, ONE_HOUR, 20),
                   retry_after(requests, now, timedelta(minutes=10), 120))
        if wait:
            return Response({'detail': '验证码请求过于频繁，请稍后重试。', 'retry_after': wait},
                            status=429, headers={'Retry-After': str(wait)})
        Reset.objects.create(email_key=email_key, ip_key=ip_key, user=find_user(email))
    return Response({'detail': ACCEPTED, 'retry_after': 60}, status=202)


def close(requests):
    requests.update(state=Reset.State.CLOSED, code_digest='', expires_at=None)


def send_mail(email, code):
    context = {'code': code}
    message = EmailMultiAlternatives(
        '【ARK GEOAI】找回密码验证码',
        render_to_string('account/password_reset_email.txt', context),
        settings.DEFAULT_FROM_EMAIL, [email],
    )
    message.attach_alternative(render_to_string('account/password_reset_email.html', context), 'text/html')
    if message.send(fail_silently=False) != 1:
        raise smtplib.SMTPException('Password reset message not accepted')


def mark_worker_ready():
    PasswordResetService.objects.update_or_create(pk=1, defaults={'worker_seen_at': timezone.now()})


def process_next_request():
    if not configured() or PasswordResetService.objects.filter(pk=1, unavailable_until__gt=timezone.now()).exists():
        return False
    candidate = Reset.objects.filter(state=Reset.State.QUEUED).order_by('pk').values('pk', 'user_id').first()
    if not candidate:
        return False
    with transaction.atomic():
        # Take the user lock before request locks, as the confirmation path does.
        user = (get_user_model().objects.select_for_update().filter(pk=candidate['user_id']).first()
                if candidate['user_id'] else None)
        queued = Reset.objects.filter(pk=candidate['pk'], state=Reset.State.QUEUED)
        job = queued.select_for_update().first()
        if not job:
            return True
        if (not user or not user.is_active or not user.has_usable_password()
                or digest('email', user.email.strip().lower()) != job.email_key
                or job.created_at <= timezone.now() - CODE_TTL
                or get_user_model().objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists()):
            close(queued)
            return True

        # Only commit a replacement after the SMTP server accepts the message.
        sent = Reset.objects.filter(user=user, email_key=job.email_key, state=Reset.State.SENT)
        if sent.filter(pk__gt=job.pk).exists():
            close(queued)
            return True
        previous = sent.only('pk', 'code_digest').first()
        code = generate_code()
        while previous and hmac.compare_digest(
            digest('code', previous.pk, user.pk, job.email_key, code), previous.code_digest
        ):
            code = generate_code()
        try:
            send_mail(user.email, code)
        except (OSError, ValueError) as error:
            logger.warning('Password reset mail failed (%s)', type(error).__name__)
            close(queued)
            if not isinstance(error, (ValueError, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError)):
                PasswordResetService.objects.filter(pk=1).update(unavailable_until=timezone.now() + COOLDOWN)
            return True
        close(sent)
        job.state = Reset.State.SENT
        job.code_digest = digest('code', job.pk, user.pk, job.email_key, code)
        job.expires_at = timezone.now() + CODE_TTL
        job.save(update_fields=['state', 'code_digest', 'expires_at'])
        return True


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def confirm(request):
    form = ConfirmInput(data=request.data)
    form.is_valid(raise_exception=True)
    if len(settings.PASSWORD_RESET_HMAC_KEY) < 32:
        return Response({'detail': UNAVAILABLE}, status=503)
    email = form.validated_data['email']
    password = form.validated_data['new_password']
    with transaction.atomic():
        user = find_user(email, lock=True)
        if not user:
            return Response({'detail': INVALID}, status=400)
        email_key = digest('email', email)
        sent = Reset.objects.filter(user=user, email_key=email_key, state=Reset.State.SENT)
        job = sent.select_for_update().order_by('-pk').first()
        if not job:
            return Response({'detail': INVALID}, status=400)
        if job.expires_at <= timezone.now():
            close(sent)
            return Response({'detail': INVALID}, status=400)
        supplied = digest('code', job.pk, user.pk, email_key, form.validated_data['code'])
        if not hmac.compare_digest(supplied, job.code_digest):
            job.failed_attempts += 1
            job.save(update_fields=['failed_attempts'])
            if job.failed_attempts >= MAX_ATTEMPTS:
                close(sent)
            return Response({'detail': INVALID}, status=400)
        try:
            validators = get_password_validators(settings.AUTH_PASSWORD_VALIDATORS or DEFAULT_RESET_VALIDATORS)
            validate_password(password, user=user, password_validators=validators)
        except ValidationError as error:
            return Response({'new_password': error.messages}, status=400)
        user.set_password(password)
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
        close(Reset.objects.filter(user=user, state__in=[Reset.State.QUEUED, Reset.State.SENT]))
    return Response({'detail': '密码修改成功。'})
