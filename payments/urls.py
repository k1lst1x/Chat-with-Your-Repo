from django.urls import path
from .views import get_payment_link, check_payment_status

urlpatterns = [
    path("pay/", get_payment_link, name="get_payment_link"),
    path("check_payment/", check_payment_status, name="check_payment_status"),
]
