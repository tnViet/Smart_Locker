from django.urls import path

from devices import views

urlpatterns = [
    path("heartbeat", views.heartbeat),
    path("sync", views.sync),
    path("commands/<int:command_id>/ack", views.command_ack),
]
