import requests
import json
import uuid
from django.conf import settings
from .models import Payment

IOKA_API_KEY = settings.IOKA_API_KEY
IOKA_API_URL = settings.IOKA_API_URL

def create_order(user, amount):
    """Создает заказ в Ioka и возвращает ссылку на оплату"""
    headers = {
        "API-KEY": IOKA_API_KEY,
        "Content-Type": "application/json"
    }

    our_order_id = str(uuid.uuid4())  # Генерируем наш уникальный ID заказа

    payload = {
        "amount": amount,  # Сумма в тиынах
        "external_id": our_order_id,  # ID заказа в нашей системе
        "currency": "KZT",  # Явно указываем валюту
        "description": f"Оплата подписки пользователем {user.email}",
    }

    response = requests.post(IOKA_API_URL, headers=headers, json=payload)
    
    try:
        response_data = response.json()
    except json.JSONDecodeError:
        response_data = {"error": "Ошибка декодирования JSON", "status_code": response.status_code}

    print("Ioka Response:", response.status_code, response_data)  # Логируем ответ

    if response.status_code == 201 and "order" in response_data:
        order_data = response_data["order"]

        # Логируем order_data перед возвратом
        print("Order Data:", order_data)

        # Проверяем, есть ли checkout_url в order_data
        checkout_url = order_data.get("checkout_url")
        print("Extracted checkout_url:", checkout_url)

        if not checkout_url:
            print("Ошибка: checkout_url отсутствует в order_data!")
            return None

        # Сохраняем платеж в БД
        Payment.objects.create(
            user=user,
            amount=amount,
            ioka_order_id=order_data["id"],
            our_order_id=our_order_id,
            status=order_data["status"]
        )

        return checkout_url  # Возвращаем URL для оплаты

    print("Ошибка создания заказа:", response_data)
    return None  # Если что-то пошло не так
