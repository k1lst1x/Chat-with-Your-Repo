from django.db import models
from django.conf import settings  # Используем AUTH_USER_MODEL из настроек Django

class Chat(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Исправлено
    message = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email}: {self.message}'  # Так как теперь email - основной логин
