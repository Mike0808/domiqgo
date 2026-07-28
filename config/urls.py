"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from importlib import import_module
from django.contrib import admin
from django.urls import include, path
from allauth.socialaccount import providers

# allauth.socialaccount.urls alone only carries the connect/signup/error
# views — it does NOT include each provider's own login/callback routes
# (that's normally allauth.urls's job, which this project avoids: it also
# bundles allauth's local-account signup/login views, defeating "no
# self-registration"). This mirrors allauth.urls's own
# build_provider_urlpatterns(): walk the registry so every REGISTERED
# provider (Yandex, VK, and Gosuslugi once billing.esia_provider registers
# it) gets its routes with no urls.py edit required per provider.
def _provider_urlpatterns():
    patterns = []
    for provider_class in providers.registry.get_class_list():
        prov_mod = import_module(f"{provider_class.get_package()}.urls")
        prov_urlpatterns = getattr(prov_mod, "urlpatterns", None)
        if prov_urlpatterns:
            patterns += prov_urlpatterns
    return patterns

# /media is intentionally NOT wired to unauthenticated static serving (even in
# DEBUG): uploads are private and go through billing.views.media_file instead.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.socialaccount.urls")),
    path("accounts/", include(_provider_urlpatterns())),
    path("", include("billing.urls")),
]
