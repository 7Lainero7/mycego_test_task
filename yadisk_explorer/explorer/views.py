import logging
from django.shortcuts import render, redirect
from django.views import View
from django.http import HttpResponse, JsonResponse
from urllib.parse import urlparse, unquote, quote
import requests

logger = logging.getLogger(__name__)


class YandexDiskView(View):
    BASE_API_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"
    DOWNLOAD_API_URL = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

    def get(self, request):
        if 'yandex_user' not in request.session:
            return render(request, 'login.html')
        return render(request, 'index.html')

    def post(self, request):
        if 'yandex_user' not in request.session:
            return redirect('index')

        public_url = request.POST.get('public_url', '').strip()
        files = []
        error = None

        if public_url:
            try:
                # Извлекаем public_key из URL
                public_key = self._extract_public_key(public_url)

                # Получаем метаинформацию
                params = {
                    'public_key': public_key,
                    'path': '',  # Корень публичной папки
                    'limit': 100,  # Лимит файлов
                    'sort': '-modified'  # Сортировка по дате изменения
                }

                response = requests.get(
                    self.BASE_API_URL,
                    params=params,
                    headers=self._get_headers(request)
                )

                self._check_response(response)

                data = response.json()
                files = self._parse_files(data, public_key)

            except Exception as e:
                error = str(e)
                logger.error(f"Error: {error}")

        return render(request, 'index.html', {
            'user': request.session['yandex_user'],
            'files': files,
            'public_url': public_url,
            'error': error
        })

    def _extract_public_key(self, url):
        """Извлекает public_key из URL Яндекс.Диска"""
        parsed = urlparse(url)
        if 'disk.yandex.ru' not in parsed.netloc:
            raise ValueError("Неверная ссылка Яндекс.Диска")

        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) >= 2 and path_parts[0] == 'd':
            return path_parts[1]
        elif 'public_key' in parsed.query:
            return parsed.query.split('public_key=')[1].split('&')[0]
        else:
            raise ValueError("Не удалось извлечь public_key из ссылки")

    def _get_headers(self, request):
        """Возвращает заголовки для API запросов"""
        return {
            'Authorization': f'OAuth {request.session.get("yandex_token", "")}',
            'Accept': 'application/json'
        }

    def _check_response(self, response):
        """Проверяет ответ API на ошибки"""
        if response.status_code == 404:
            error_msg = response.json().get('message', 'Ресурс не найден')
            raise ValueError(
                f"{error_msg}. Убедитесь, что:\n"
                "1. Ссылка корректная и публичная\n"
                "2. Папка/файл явно опубликованы (не просто расшарены)"
            )
        elif response.status_code != 200:
            error_msg = response.json().get('message', 'Неизвестная ошибка API')
            raise ValueError(f"Ошибка API ({response.status_code}): {error_msg}")

    def _parse_files(self, data, public_key):
        """Парсит список файлов из ответа API"""
        items = []
        if '_embedded' in data and 'items' in data['_embedded']:
            for item in data['_embedded']['items']:
                if item['type'] == 'file':  # Только файлы
                    items.append({
                        'name': item['name'],
                        'path': quote(item['path']),
                        'size': item.get('size', 0),
                        'modified': item.get('modified', ''),
                        'media_type': item.get('mime_type', 'unknown'),
                        'public_key': public_key,
                        'preview': item.get('preview', ''),
                        'md5': item.get('md5', '')
                    })
        return items


class IndexView(View):
    def get(self, request):
        if 'yandex_user' not in request.session:
            return render(request, 'login.html')
        return render(request, 'index.html')

    def post(self, request):
        if 'yandex_user' not in request.session:
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

                path_parts = parsed.path.split('/')
                if len(path_parts) >= 3 and path_parts[1] == 'd':
                    public_key = path_parts[2]
                else:
                    raise ValueError("Неверный формат ссылки. Пример: https://disk.yandex.ru/d/AbCdEfGhIjKlMn")

                # Запрос метаинформации
                api_url = "https://cloud-api.yandex.net/v1/disk/public/resources"
                params = {
                    'public_key': public_key,
                    'path': 'disk:/'  # Важно: путь должен начинаться с disk:/
                }

                logger.debug(f"Requesting Yandex API with params: {params}")

                response = requests.get(api_url, params=params)

                if response.status_code != 200:
                    error_msg = response.json().get('message', 'Неизвестная ошибка API')
                    logger.error(f"API error: {error_msg} (status: {response.status_code})")
                    raise ValueError(f"Ошибка API: {error_msg}")

                data = response.json()
                logger.debug(f"API response: {data}")

                if '_embedded' not in data:
                    raise ValueError("Папка пуста или не является публичной")

                files = self._parse_files(data, public_key)

            except Exception as e:
                error = str(e)
                logger.error(f"Error processing request: {error}")

        return render(request, 'index.html', {
            'user': request.session['yandex_user'],
            'files': files,
            'public_url': public_url,
            'error': error
        })

    def _parse_files(self, data, public_key):
        items = []
        if '_embedded' in data and 'items' in data['_embedded']:
            for item in data['_embedded']['items']:
                if item['type'] == 'file':
                    items.append({
                        'name': item['name'],
                        'path': quote(item['path']),  # Кодируем путь для URL
                        'size': item.get('size', 0),
                        'public_key': public_key,
                        'media_type': item.get('media_type', 'unknown'),
                        'modified': item.get('modified', '')
                    })
        return items


class DownloadView(YandexDiskView):
    def get(self, request):
        if 'yandex_user' not in request.session:
            return redirect('index')

        try:
            file_path = unquote(request.GET.get('path', ''))
            public_key = request.GET.get('public_key', '')

            if not file_path or not public_key:
                raise ValueError("Не указаны path и public_key")

            # 1. Получаем временную ссылку для скачивания
            download_params = {
                'public_key': public_key,
                'path': file_path
            }

            response = requests.get(
                self.DOWNLOAD_API_URL,
                params=download_params,
                headers=self._get_headers(request),
                timeout=10
            )

            self._check_response(response)
            download_url = response.json().get('href')

            if not download_url:
                raise ValueError("Не удалось получить ссылку для скачивания")

            # 2. Скачиваем файл по полученной ссылке
            file_response = requests.get(
                download_url,
                stream=True,
                headers=self._get_headers(request),
                timeout=30
            )
            file_response.raise_for_status()

            # Определяем имя файла и тип содержимого
            filename, content_type = self._get_file_info(file_response, file_path)

            # Отправляем файл пользователю
            response = HttpResponse(
                file_response.iter_content(chunk_size=8192),
                content_type=content_type
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return render(request, 'index.html', {
                'user': request.session['yandex_user'],
                'error': str(e)
            })

    def _get_file_info(self, response, fallback_path):
        """Определяет имя файла и тип содержимого"""
        # Из заголовков
        content_disposition = response.headers.get('Content-Disposition', '')
        content_type = response.headers.get('content-type', 'application/octet-stream')

        if 'filename=' in content_disposition:
            filename = content_disposition.split('filename=')[1].strip('"\'')
        else:
            filename = unquote(fallback_path.split('/')[-1] or 'file')

        return filename, content_type


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


class LogoutView(View):
    def get(self, request):
        request.session.flush()
        return redirect('index')

