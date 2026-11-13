from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("devices.urls")),
    path("api/v1/", include("lockers.urls")),
    path("api/v1/", include("payments.urls")),
    path("api/v1/", include("dashboard.urls")),
]

handler404 = "config.common.not_found"
handler500 = "config.common.server_error"
