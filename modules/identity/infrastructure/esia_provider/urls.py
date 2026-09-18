from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns
from .provider import ESIAProvider

urlpatterns = default_urlpatterns(ESIAProvider)
