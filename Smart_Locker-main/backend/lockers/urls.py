from django.urls import path

from lockers import views

urlpatterns = [
    path("scan", views.scan),
    path("events", views.events),
    path("events/batch", views.events_batch),
]
