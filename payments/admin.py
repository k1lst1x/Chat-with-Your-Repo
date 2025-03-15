from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount_display", "ioka_order_id", "our_order_id", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("ioka_order_id", "our_order_id", "user__email", "user__username")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description="Сумма (₸)")
    def amount_display(self, obj):
        return f"{obj.amount / 100:.2f}"

