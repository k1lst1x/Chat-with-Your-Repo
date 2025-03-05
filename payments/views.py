import requests
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from .payments import create_order

from django.conf import settings

IOKA_API_KEY = settings.IOKA_API_KEY

@login_required
@csrf_exempt
def get_payment_link(request):
    user = request.user
    amount = 50000  # Цена подписки в тиынах (500 тенге)

    checkout_url = create_order(user, amount)

    print("Возвращаемый checkout_url из create_order:", checkout_url)  # Проверяем, что получаем
    
    if checkout_url:
        return JsonResponse({"url": checkout_url})

    return JsonResponse({"error": "Ошибка при создании заказа. Проверьте логи сервера!"}, status=400)

@csrf_exempt
@login_required
def check_payment_status(request):
    user = request.user
    payment = user.payments.filter(status="UNPAID").last()

    if not payment:
        return JsonResponse({"error": "Нет активного платежа"}, status=400)

    url = f"https://stage-api.ioka.kz/v2/orders/{payment.ioka_order_id}"
    headers = {"API-KEY": IOKA_API_KEY}

    response = requests.get(url, headers=headers)

    try:
        response_data = response.json()
    except requests.exceptions.JSONDecodeError:
        return JsonResponse({"error": "Ошибка декодирования JSON", "raw_response": response.text}, status=500)

    print("Ioka API Response:", response_data)  # Логируем ответ

    if response.status_code == 200:
        order_data = response_data  # Здесь теперь сразу объект заказа

        print("Order Data:", order_data)

        if order_data["status"] == "PAID":
            payment.status = "PAID"
            payment.save()

            user.is_subscribed = True
            user.save()

            return JsonResponse({"message": "Подписка активирована!"})
        else:
            return JsonResponse({"status": order_data["status"]})

    return JsonResponse({"error": "Ошибка запроса к Ioka", "response": response_data}, status=400)

