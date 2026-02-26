from django.urls import path

from . import views

app_name = 'producers'

urlpatterns = [
    path('profile/edit/', views.edit_profile, name='edit_profile'),
]
