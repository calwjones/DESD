from django.urls import path

from . import views

app_name = 'producers'

urlpatterns = [
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('settlements/', views.settlements_list, name='settlements_list'),
    path('settlements/<int:settlement_id>/', views.settlement_detail, name='settlement_detail'),
    path('settlements/<int:settlement_id>/csv/', views.settlement_csv, name='settlement_csv'),
]
