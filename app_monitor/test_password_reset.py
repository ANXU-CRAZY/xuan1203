import os
import smtplib
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import close_old_connections, connections
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from config.smtp_settings import load_smtp_settings
from . import password_reset as reset
from .models import PasswordResetRequest as Reset, PasswordResetService


MAIL_SETTINGS = dict(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                     EMAIL_HOST_USER='sender@163.com', EMAIL_HOST_PASSWORD='test-password',
                     DEFAULT_FROM_EMAIL='sender@163.com', PASSWORD_RESET_HMAC_KEY='test-key-' * 8,
                     PASSWORD_RESET_TRUST_PROXY=False)
OLD_PASSWORD = 'OriginalPass-Z4w7!'
NEW_PASSWORD = 'ReplacedPass-M7s3!'


class PasswordResetSettingsTests(SimpleTestCase):
    def test_uses_cryptographic_generator_and_preserves_leading_zero(self):
        with patch.object(reset.secrets, 'randbelow', return_value=17) as random:
            self.assertEqual(reset.generate_code(), '000017')
            random.assert_called_once_with(1_000_000)

    def test_reads_files_and_environment_overrides(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            path = Path(folder)
            (path / '.env').write_text('SMTP_USER=first@163.com\nSMTP_PASSWORD="file-test"\n')
            (path / '.env.local').write_text('SMTP_USER=second@163.com\nSMTP_FROM=second@163.com\n')
            with patch.dict(os.environ, {'SMTP_PASSWORD': 'env-test'}):
                settings = load_smtp_settings(path)
            self.assertEqual(settings['EMAIL_HOST'], 'smtp.163.com')
            self.assertEqual(settings['EMAIL_PORT'], 465)
            self.assertTrue(settings['EMAIL_USE_SSL'])
            self.assertFalse(settings['EMAIL_USE_TLS'])
            self.assertEqual(settings['EMAIL_HOST_USER'], 'second@163.com')
            self.assertEqual(settings['EMAIL_HOST_PASSWORD'], 'env-test')
            self.assertEqual(settings['DEFAULT_FROM_EMAIL'], 'second@163.com')


class ResetRequests:
    def send(self, email=None, client=None):
        return (client or self.client).post(reverse('password_reset_send'), {'email': email or self.user.email},
                                            content_type='application/json')

    def confirm(self, code, *, email=None, password=NEW_PASSWORD, client=None):
        return (client or self.client).post(reverse('password_reset_confirm'), {
            'email': email or self.user.email, 'code': code, 'new_password': password, 'confirm_password': password,
        }, content_type='application/json')

    def make_user(self):
        self.user = get_user_model().objects.create_user('reset-member', 'Birds@163.com', OLD_PASSWORD)
        reset.mark_worker_ready()

    def issue_code(self, code='004297'):
        self.assertEqual(self.send().status_code, 202)
        with patch.object(reset, 'generate_code', return_value=code):
            self.assertTrue(reset.process_next_request())
        return Reset.objects.get(state=Reset.State.SENT)


@override_settings(**MAIL_SETTINGS)
class PasswordResetTests(ResetRequests, TestCase):
    def setUp(self):
        self.make_user()

    def test_staff_can_reset_password_and_log_in_to_admin(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.issue_code()
        self.assertEqual(self.confirm('004297').status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(OLD_PASSWORD))
        response = self.client.post('/admin/login/?next=/admin/', {
            'username': self.user.username, 'password': NEW_PASSWORD, 'next': '/admin/',
        })
        self.assertRedirects(response, '/admin/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_email_templates_and_no_plaintext_storage(self):
        queued = self.send(self.user.email.upper())
        self.assertEqual(queued.status_code, 202)
        self.assertEqual(queued.json(), {'detail': reset.ACCEPTED, 'retry_after': 60})
        self.assertFalse(mail.outbox)
        self.assertEqual(Reset.objects.get().code_digest, '')
        with patch.object(reset, 'generate_code', return_value='004297'):
            reset.process_next_request()
        job = Reset.objects.get()
        self.assertEqual(job.state, Reset.State.SENT)
        self.assertRegex(job.code_digest, r'^[0-9a-f]{64}$')
        self.assertNotEqual(job.code_digest, '004297')
        self.assertGreater(job.expires_at, timezone.now() + timedelta(minutes=4, seconds=59))
        message, = mail.outbox
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.subject, '【ARK GEOAI】找回密码验证码')
        for content in (message.body, message.alternatives[0].content):
            self.assertIn('004297', content)
            self.assertIn('5 分钟', content)
            self.assertNotRegex(content, r'https?://')
        self.assertEqual(message.alternatives[0].mimetype, 'text/html')

    def test_resets_password_revokes_tokens_and_django_sessions(self):
        old_token = Token.objects.create(user=self.user)
        session = Client()
        session.force_login(self.user)
        self.issue_code()
        self.assertEqual(self.confirm('004297').status_code, 200)
        self.assertEqual(self.confirm('004297').status_code, 400)
        job = Reset.objects.get()
        self.assertEqual(job.state, Reset.State.CLOSED)
        self.assertEqual(job.code_digest, '')
        self.assertFalse(Token.objects.filter(key=old_token.key).exists())
        self.assertEqual(session.get(reverse('account_entry')).status_code, 200)
        self.assertEqual(self.client.get(reverse('user-me'), HTTP_AUTHORIZATION='Token ' + old_token.key).status_code, 401)
        for password, status in ((OLD_PASSWORD, 400), (NEW_PASSWORD, 200)):
            self.assertEqual(self.client.post(reverse('api_token_auth'), {
                'username': self.user.username, 'password': password,
            }).status_code, status)

    def test_wrong_code_expires_after_five_attempts(self):
        job = self.issue_code()
        for attempt in range(1, 6):
            self.assertEqual(self.confirm('000000').json(), {'detail': reset.INVALID})
            job.refresh_from_db()
            self.assertEqual(job.failed_attempts, attempt)
            self.assertEqual(job.state, Reset.State.CLOSED if attempt == 5 else Reset.State.SENT)
        self.assertEqual(self.confirm('004297').status_code, 400)

    def test_expired_code_is_cleared(self):
        job = self.issue_code()
        Reset.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.confirm('004297').json(), {'detail': reset.INVALID})
        job.refresh_from_db()
        self.assertEqual(job.code_digest, '')

    def test_password_validators_run_before_consumption(self):
        self.issue_code()
        response = self.confirm('004297', password='12345678')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.json())
        self.assertEqual(self.confirm('004297').status_code, 200)

    def test_resend_cooldown_and_old_code_invalidation(self):
        old_job = self.issue_code()
        limited = self.send(self.user.email.upper())
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited['Retry-After'], '60')
        Reset.objects.filter(pk=old_job.pk).update(created_at=timezone.now() - timedelta(seconds=61))
        self.assertEqual(self.send().status_code, 202)
        with patch.object(reset, 'generate_code', side_effect=['004297', '654321']):
            self.assertTrue(reset.process_next_request())
        old_job.refresh_from_db()
        self.assertEqual(old_job.code_digest, '')
        self.assertEqual(self.confirm('004297').status_code, 400)
        self.assertEqual(self.confirm('654321').status_code, 200)

    def test_email_ip_and_global_rate_limits(self):
        now = timezone.now()
        email_key = reset.digest('email', self.user.email.lower())
        ip_key = reset.digest('ip', '127.0.0.1')
        Reset.objects.bulk_create([Reset(email_key=email_key, ip_key=ip_key) for _ in range(5)])
        Reset.objects.update(created_at=now - timedelta(minutes=2))
        self.assertEqual(self.send().status_code, 429)
        Reset.objects.bulk_create([Reset(email_key='other', ip_key=ip_key) for _ in range(15)])
        self.assertEqual(self.send('other@163.com').status_code, 429)
        Reset.objects.bulk_create([Reset(email_key='other', ip_key='other') for _ in range(100)])
        response = self.client.post(reverse('password_reset_send'), {'email': 'other@163.com'},
                                    content_type='application/json', REMOTE_ADDR='192.0.2.3')
        self.assertEqual(response.status_code, 429)

    def test_unknown_inactive_and_ambiguous_email_have_identical_responses(self):
        users = get_user_model().objects
        users.create_user('inactive', 'inactive@163.com', OLD_PASSWORD, is_active=False)
        users.create_user('duplicate-one', 'duplicate@163.com', OLD_PASSWORD)
        users.create_user('duplicate-two', 'DUPLICATE@163.com', OLD_PASSWORD)
        emails = [self.user.email, 'missing@163.com', 'inactive@163.com', 'duplicate@163.com']
        responses = [self.send(email) for email in emails]
        self.assertTrue(all(item.status_code == 202 and item.json() == responses[0].json() for item in responses))
        for _ in emails:
            self.assertTrue(reset.process_next_request())
        self.assertEqual(len(mail.outbox), 1)
        for email in emails[1:]:
            self.assertEqual(self.confirm('004297', email=email).json(), {'detail': reset.INVALID})

    def test_email_change_or_deactivation_invalidates_pending_or_issued_codes(self):
        self.issue_code()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.confirm('004297').status_code, 400)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=True, email='different@163.com')
        self.assertEqual(self.confirm('004297').status_code, 400)
        self.assertEqual(self.confirm('004297', email='different@163.com').status_code, 400)

    def test_smtp_failures_never_activate_a_code_or_expose_exception_details(self):
        for exception in [smtplib.SMTPAuthenticationError(535, b'PRIVATE'), TimeoutError('PRIVATE'),
                          smtplib.SMTPRecipientsRefused({'private@163.com': (550, b'PRIVATE')})]:
            with self.subTest(exception=type(exception).__name__):
                Reset.objects.all().delete()
                PasswordResetService.objects.update(unavailable_until=None)
                response = self.send()
                self.assertEqual(response.json()['detail'], reset.ACCEPTED)
                with patch.object(reset, 'send_mail', side_effect=exception), self.assertLogs(reset.__name__) as logs:
                    self.assertTrue(reset.process_next_request())
                self.assertNotIn('PRIVATE', ''.join(logs.output))
                self.assertEqual(Reset.objects.get().state, Reset.State.CLOSED)
                self.assertEqual(Reset.objects.get().code_digest, '')
                if not isinstance(exception, smtplib.SMTPRecipientsRefused):
                    self.assertEqual(self.send('missing@163.com').status_code, 503)

    def test_failed_resend_keeps_the_previous_working_code(self):
        old_job = self.issue_code()
        Reset.objects.filter(pk=old_job.pk).update(created_at=timezone.now() - timedelta(seconds=61))
        self.assertEqual(self.send().status_code, 202)
        with patch.object(reset, 'send_mail', side_effect=TimeoutError), self.assertLogs(reset.__name__):
            reset.process_next_request()
        self.assertEqual(self.confirm('004297').status_code, 200)

    def test_reports_unavailability_without_a_live_worker(self):
        PasswordResetService.objects.update(worker_seen_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.send().status_code, 503)
        self.assertEqual(self.send('missing@163.com').status_code, 503)


@override_settings(**MAIL_SETTINGS)
class PasswordResetConcurrencyTests(ResetRequests, TransactionTestCase):
    def setUp(self):
        self.make_user()

    def race(self, request):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return request(Client()).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(future.result(timeout=15) for future in [pool.submit(run), pool.submit(run)])

    def test_only_one_request_passes_the_concurrent_cooldown(self):
        self.assertEqual(self.race(lambda client: self.send(client=client)), [202, 429])
        self.assertEqual(Reset.objects.count(), 1)

    def test_only_one_parallel_submission_consumes_the_code(self):
        self.issue_code()
        self.assertEqual(self.race(lambda client: self.confirm('004297', client=client)), [200, 400])
        self.assertEqual(Reset.objects.get().code_digest, '')
