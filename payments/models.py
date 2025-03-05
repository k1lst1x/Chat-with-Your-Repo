from django.db import models
from django.conf import settings

class Payment(models.Model):
    STATUS_CHOICES = [
        ("UNPAID", "Не оплачено"),
        ("PAID", "Оплачено"),
        ("EXPIRED", "Истекло"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    amount = models.IntegerField(help_text="Сумма в тиынах (1 тенге = 100 тиын)")
    ioka_order_id = models.CharField(max_length=255, unique=True, help_text="ID заказа в Ioka")
    our_order_id = models.CharField(max_length=255, unique=True, help_text="Наш ID заказа")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="UNPAID")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Платеж {self.ioka_order_id} - {self.status}"
