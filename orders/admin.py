from django.contrib import admin
from .models import Order, OrderItem, Payment, PaymentSplit



class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]


class PaymentSplitInline(admin.TabularInline):
    model = PaymentSplit
    extra = 0
    readonly_fields = ("producer", "gross_amount", "commission_amount", "net_amount")


class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "amount", "commission_amount", "producer_net", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("stripe_session_id", "stripe_payment_intent_id", "order__id")
    readonly_fields = ("created_at",)
    inlines = [PaymentSplitInline]


admin.site.register(Order, OrderAdmin)
admin.site.register(OrderItem)
admin.site.register(Payment, PaymentAdmin)