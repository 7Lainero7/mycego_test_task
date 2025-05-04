import os
import requests

from django.shortcuts import render, redirect
from django.conf import settings
from django.views import View
from urllib.parse import urlparse, parse_qs


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
        if 'yandex_token' not in request.session:
            return render(request, 'login.html')

        return render(request, 'index.html', {
            'user': request.session['yandex_user']
        })

    def post(self, request):
        if 'yandex_token' not in request.session:
            return redirect('index')

        public_url = request.POST.get('public_url', '').strip()
        files = []
        error = None

        if public_url:
            try:
                # Извлекаем public_key из URL
                parsed = urlparse(public_url)
                if 'disk.yandex.ru' not in parsed.netloc:
                    raise ValueError("Неверная ссылка Яндекс.Диска")

                public_key = parse_qs(parsed.query).get('public_key', [None])[0]
                if not public_key:
                    raise ValueError("Ссылка должна содержать public_key")

                # Получаем список файлов
                headers = {
                    'Authorization': f'OAuth {request.session["yandex_token"]}',
                    'Accept': 'application/json'
                }
                response = requests.get(
                    f'https://cloud-api.yandex.net/v1/disk/public/resources?public_key={public_key}',
                    headers=headers
                )

                if response.status_code != 200:
                    raise ValueError(f"Ошибка API: {response.json().get('message', 'Неизвестная ошибка')}")

                data = response.json()
                files = self._parse_files(data)

            except Exception as e:
                error = str(e)

        return render(request, 'index.html', {
            'user': request.session['yandex_user'],
            'files': files,
            'public_url': public_url,
            'error': error
        })

    def parse_files(data):
        items = []
        if '_embedded' in data and 'items' in data['_embedded']:
            for item in data['_embedded']['items']:
                items.append({
                    'name': item['name'],
                    'type': 'dir' if item['type'] == 'dir' else 'file',
                    'path': item['path'],
                    'size': item.get('size', 0),
                    'download_url': item.get('file', None)
                })
        return items


class DownloadView(View):
    def get(self, request):
        if 'yandex_token' not in request.session:
            return redirect('index')

        file_url = request.GET.get('url')
        if not file_url:
            return render(request, 'index.html', {
                'user': request.session['yandex_user'],
                'error': 'Не указан URL файла'
            })

        try:
            # Получаем прямую ссылку для скачивания
            headers = {
                'Authorization': f'OAuth {request.session["yandex_token"]}',
                'Accept': 'application/json'
            }
            response = requests.get(
                f'https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={file_url}',
                headers=headers
            )

            if response.status_code != 200:
                raise ValueError(f"Ошибка получения ссылки: {response.json().get('message', 'Неизвестная ошибка')}")

            download_url = response.json().get('href')
            file_response = requests.get(download_url, stream=True)

            # Получаем имя файла из URL
            filename = download_url.split('/')[-1].split('?')[0]

            # Отправляем файл пользователю
            response = HttpResponse(file_response.content, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            return render(request, 'index.html', {
                'user': request.session['yandex_user'],
                'error': str(e)
            })


class LogoutView(View):

    def get(self, request):
        request.session.flush()
        return redirect('index')