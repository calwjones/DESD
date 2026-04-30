from django.urls import path
from . import views

app_name = 'delivery'

urlpatterns = [
    path('logistics/', views.logistics_dashboard, name='logistics_dashboard'),
    path('<int:delivery_id>/status/', views.update_delivery_status, name='update_status'),
]