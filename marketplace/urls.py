"""
URL configuration for marketplace project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from ai_logs.views import resolve_challenge

from . import views

from orders.api import OrderHistoryViewSet
from ai_logs.api import AIInteractionViewSet
from rest_framework.routers import DefaultRouter
from products.api import ProductViewSet

router = DefaultRouter()
router.register(r'order-history', OrderHistoryViewSet, basename='order-history')
router.register(r'ai-logs', AIInteractionViewSet)
router.register(r'products', ProductViewSet)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('products/', include('products.urls')),
    path('producers/', include('producers.urls')),
    path('', views.marketplace_view, name='marketplace'),
    path('dashboard/', views.producer_dashboard_view, name='producer_dashboard'),
    path('delivery/', include('delivery.urls')),
    path("orders/", include("orders.urls")),
    path('api/ai-logs/<int:pk>/resolve/', resolve_challenge, name='resolve_challenge'),
    path('api/', include(router.urls)), 
    path('api-auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
