from django.contrib import admin
from .models import Order, OrderItem, Payment



class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]


class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("stripe_session_id", "stripe_payment_intent_id", "order__id")
    readonly_fields = ("created_at",)


admin.site.register(Order, OrderAdmin)
admin.site.register(OrderItem)
admin.site.register(Payment, PaymentAdmin)