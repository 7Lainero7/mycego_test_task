import requests

from django.shortcuts import render, redirect
from django.conf import settings
from django.views import View


class YandexAuthView(View):
    def get(self, request):
        auth_url = (
            f"https://oauth.yandex.ru/authorize?"
            f"response_type=code&"
            f"client_id={settings.YANDEX_CLIENT_ID}&"
            f"redirect_uri={settings.YANDEX_REDIRECT_URI}"
        )
        return redirect(auth_url)


class YandexAuthCallbackView(View):
    def get(self, request):
        code = request.GET.get('code')
        if not code:
            return render(request, 'error.html', {'error': 'Authorization failed'})

        # Получаем токен
        token_url = "https://oauth.yandex.ru/token"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': settings.YANDEX_CLIENT_ID,
            'client_secret': settings.YANDEX_CLIENT_SECRET
        }
        response = requests.post(token_url, data=data)

        if response.status_code != 200:
            return render(request, 'error.html', {'error': 'Token request failed'})

        access_token = response.json().get('access_token')
        request.session['yandex_token'] = access_token

        # Получаем информацию о пользователе
        user_info = requests.get(
            "https://login.yandex.ru/info",
            headers={'Authorization': f'OAuth {access_token}'}
        ).json()

        request.session['yandex_user'] = {
            'login': user_info.get('login'),
            'name': user_info.get('real_name'),
            'email': user_info.get('default_email')
        }

        return redirect('index')


class IndexView(View):
    def get(self, request):
        user = request.session.get('yandex_user')
        if not user:
            return render(request, 'login.html')

        return render(request, 'index.html', {'user': user})