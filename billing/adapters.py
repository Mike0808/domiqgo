from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect, render
from modules.identity import api as identity
from .consent import PRIVACY_POLICY_VERSION

class NoSignupSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Enforces two rules everywhere, not just in the UI:
    1. OAuth can never create a new account — a tenant record must already
       exist (landlord-issued username/password).
    2. Any account — tenant or landlord — may only CONNECT a new provider
       after giving 152-FZ consent for the current policy version.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return  # already linked -> ordinary login, proceed
        if request.user.is_authenticated:
            # Согласие спрашивается у Identity: оно принадлежит учётной записи
            # и хранится журналом (шаг C4a). Профиль жильца не проверяется —
            # именно эта проверка замыкала владельца в круг (дефект №33,
            # шаг C4b).
            if not identity.has_current_consent(
                    request.user.pk, PRIVACY_POLICY_VERSION):
                raise ImmediateHttpResponse(redirect("oauth_connections"))
            return  # consent on file -> allow attaching the new provider
        raise ImmediateHttpResponse(
            render(request, "billing/oauth_not_linked.html", status=403))
