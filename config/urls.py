from django.contrib import admin
from django.urls import include, path

from .login import LoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/", include("catalog.urls")),
    path("api/", include("orders.urls")),
]
