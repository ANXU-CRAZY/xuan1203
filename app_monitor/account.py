"""Shared entry for session-based admin and token-based platform accounts."""
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


def destination(user):
    return reverse('admin:index' if user.is_staff else 'profile')


@method_decorator(csrf_protect, name='dispatch')
class PlatformLoginView(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'next_url': destination(user)})


@require_GET
def entry(request):
    if request.user.is_authenticated:
        return redirect(destination(request.user))
    return render(request, 'account-entry.html')


@require_GET
def login_page(request):
    if request.user.is_authenticated:
        return redirect(destination(request.user))
    return render(request, 'login.html')


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
