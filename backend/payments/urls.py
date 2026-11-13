from django.urls import path

from payments import views

urlpatterns = [
    path("payment/check", views.payment_check),
    path("payments/callback", views.payments_callback),
]
