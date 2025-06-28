from django.urls import path, include
from . import views

# Payment URLs
payment_urlpatterns = [
    path('initiate/', views.initiate_payment, name='initiate-payment'),
    path('verify/<str:reference>/', views.verify_payment, name='verify-payment'),
    path('webhook/', views.payment_webhook, name='payment-webhook'),
    path('status/<uuid:payment_id>/', views.payment_status, name='payment-status'),
    path('history/', views.user_payments, name='user-payments'),
]

# Main URL patterns (add to existing urls.py)
urlpatterns = [
    # ... existing URL patterns ...
    path('api/payments/', include(payment_urlpatterns)),
]