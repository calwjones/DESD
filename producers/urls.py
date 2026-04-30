from django.urls import path
from . import views

app_name = 'producers'

urlpatterns = [
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('settlements/', views.settlements_list, name='settlements_list'),
    path('settlements/<int:settlement_id>/', views.settlement_detail, name='settlement_detail'),
    path('settlements/<int:settlement_id>/csv/', views.settlement_csv, name='settlement_csv'),
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('recipes/add/', views.recipe_add, name='recipe_add'),
    path('recipes/<int:pk>/edit/', views.recipe_edit, name='recipe_edit'),
    path('recipes/<int:pk>/delete/', views.recipe_delete, name='recipe_delete'),
    path('recipes/<int:pk>/', views.recipe_detail, name='recipe_detail'),
    path('stories/', views.story_list, name='story_list'),
    path('stories/add/', views.story_add, name='story_add'),
    path('stories/<int:pk>/edit/', views.story_edit, name='story_edit'),
    path('stories/<int:pk>/delete/', views.story_delete, name='story_delete'),
    path('<int:pk>/', views.producer_public_profile, name='producer_public_profile'),
]