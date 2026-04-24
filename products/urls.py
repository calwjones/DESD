from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('<int:pk>/', views.product_detail, name='detail'),
    path('add/', views.product_add, name='add'),
    path('<int:pk>/edit/', views.product_edit, name='edit'),
    path('<int:pk>/delete/', views.product_delete, name='delete'),
    path('<int:pk>/challenge/', views.challenge_grade, name='challenge_grade'),
]
