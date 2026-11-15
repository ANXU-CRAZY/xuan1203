from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods


@csrf_protect
@require_http_methods(['GET', 'POST'])
def sign_in(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = ''
    if request.method == 'POST':
        # The dedicated reverse proxy overwrites X-Real-IP for every request.
        key = 'geostudio:login:' + request.META.get('HTTP_X_REAL_IP', request.META.get('REMOTE_ADDR', ''))
        cache.add(key, 0, 60)
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.set(key, 1, 60)
            attempts = 1
        if attempts > 10:
            return render(request, 'geostudio-login.html', {'error': '尝试过于频繁，请稍后再试。'}, status=429)
        user = authenticate(request, username=request.POST.get('username', ''), password=request.POST.get('password', ''))
        if user is not None and user.is_active:
            login(request, user)
            return redirect('home')
        error = '用户名或密码错误，请重试。'
    return render(request, 'geostudio-login.html', {'error': error})


@csrf_protect
@require_http_methods(['POST'])
def sign_out(request):
    logout(request)
    return redirect('home')
