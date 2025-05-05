from django.db import models
from django.utils import timezone
from datetime import timedelta


class FileCache(models.Model):
    cache_key = models.CharField(max_length=255, unique=True)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    @classmethod
    def set(cls, key, value, ttl=3600):
        expires_at = timezone.now() + timedelta(seconds=ttl)
        cls.objects.update_or_create(
            cache_key=key,
            defaults={'data': value, 'expires_at': expires_at}
        )

    @classmethod
    def get(cls, key):
        try:
            entry = cls.objects.get(cache_key=key, expires_at__gt=timezone.now())
            return entry.data
        except cls.DoesNotExist:
            return None

    @classmethod
    def clear_expired(cls):
        cls.objects.filter(expires_at__lte=timezone.now()).delete()