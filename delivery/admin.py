from django.contrib import admin
from .models import Delivery

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('order', 'scheduled_date', 'scheduled_time_slot', 'status')
    list_filter = ('status', 'scheduled_date', 'scheduled_time_slot')
    date_hierarchy = 'scheduled_date'
    ordering = ('scheduled_date', 'scheduled_time_slot')
    search_fields = ('order__id', 'delivery_address')