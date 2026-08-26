from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect, render
from modules.identity import api as identity
from .consent import PRIVACY_POLICY_VERSION

class NoSignupSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Enforces two rules everywhere, not just in the UI:
    1. OAuth can never create a new account — a tenant record must already
       exist (landlord-issued username/password).
    2. A tenant may only CONNECT a new provider to their own account after
       giving 152-FZ consent for the current policy version.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return  # already linked -> ordinary login, proceed
        if request.user.is_authenticated:
            # Согласие спрашивается у Identity: оно принадлежит учётной записи
            # и хранится журналом (шаг C4a). Проверка профиля жильца пока
            # остаётся — это и есть дефект №33, из-за которого владелец ходит
            # по кругу; он чинится следующим шагом, отдельно от переноса
            # (правило 7.4).
            tenant = getattr(request.user, "tenant", None)
            if tenant is None or not identity.has_current_consent(
                    request.user.pk, PRIVACY_POLICY_VERSION):
                raise ImmediateHttpResponse(redirect("oauth_connections"))
            return  # consent on file -> allow attaching the new provider
        raise ImmediateHttpResponse(
            render(request, "billing/oauth_not_linked.html", status=403))
