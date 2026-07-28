from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .webhooks import telegram_webhook

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("bot/telegram/webhook/", telegram_webhook, name="telegram_webhook"),
    path("", views.current_month, name="current_month"),
    path("history/", views.history, name="history"),
    path("documents/", views.documents, name="documents"),
    path("media/<path:path>", views.media_file, name="media_file"),
    path("connections/", views.oauth_connections, name="oauth_connections"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
]
