from django.urls import path

from dashboard import views

urlpatterns = [
    path("auth/login", views.login),
    path("compartments", views.compartments),
    path("sessions", views.sessions),
    path("sessions/<int:session_id>", views.session_detail),
    path("sessions/<int:session_id>/pay", views.session_pay),
    path("users", views.users),
    path("users/<int:user_id>", views.user_update),
    path("stats/overview", views.stats_overview),
    path("stats/revenue", views.stats_revenue),
    path("devices", views.devices),
    path("admin/open", views.admin_open),
    path("admin/reset", views.admin_reset),
    path("fee-rules", views.fee_rules),
]
