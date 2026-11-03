from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from .login import LoginView


def health(request):
    """Open endpoint for uptime pings, so the free Render service doesn't go to sleep."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/", include("catalog.urls")),
    path("api/", include("orders.urls")),
]
