from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    email = models.EmailField(_('email address'), unique=True)
    is_subscribed = models.BooleanField(default=False, help_text="Подписка активна")

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
