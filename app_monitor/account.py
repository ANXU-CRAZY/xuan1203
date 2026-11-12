"""Shared entry for session-based admin and token-based platform accounts."""
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


def destination(user):
    return reverse('admin:index' if user.is_staff else 'profile')


class PlatformTokenView(ObtainAuthToken):
    starts_session = False

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        authenticated = serializer.validated_data['user']
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().filter(pk=authenticated.pk).first()
            if not user or not user.is_active or user.password != authenticated.password:
                raise ValidationError({'detail': '用户名或密码错误。'})
            token, _ = Token.objects.get_or_create(user=user)
            result = {'token': token.key}
            if self.starts_session:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                result['next_url'] = destination(user)
        return Response(result)


@method_decorator(csrf_protect, name='dispatch')
class PlatformLoginView(PlatformTokenView):
    starts_session = True


@require_GET
def entry(request):
    if request.user.is_authenticated:
        return redirect(destination(request.user))
    return render(request, 'account-entry.html')


@require_GET
def login_page(request):
    if request.user.is_authenticated:
        return redirect(destination(request.user))
    admin_reset = request.GET.get('role') == 'admin'
    return render(request, 'login.html', {
        'admin_password_reset': admin_reset,
        'reset_login_url': reverse('admin:login' if admin_reset else 'login'),
    })


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def restore_session(request):
    login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
    return Response({'next_url': destination(request.user)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sign_out(request):
    logout(request)
    return Response({'detail': '已退出登录'})
