from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.current_month, name="current_month"),
    path("history/", views.history, name="history"),
    path("documents/", views.documents, name="documents"),
    path("media/<path:path>", views.media_file, name="media_file"),
]
