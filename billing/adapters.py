"""Адаптер allauth — тонкая обёртка над решением Identity.

Правила входа через провайдера живут в домене Identity (шаг C4d):
`admit_external_login` говорит, что делать с пришедшей внешней личностью,
а здесь его ответ переводится в HTTP — пропустить, отправить за согласием
или отказать. Ни одного «если» о самих правилах тут нет и быть не должно.
"""

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect, render

from modules.identity import api as identity
from modules.identity.api import ExternalLoginDecision

from .consent import PRIVACY_POLICY_VERSION


class NoSignupSocialAccountAdapter(DefaultSocialAccountAdapter):

    def is_open_for_signup(self, request, sociallogin):
        # Страховка на уровне фреймворка: инвариант 1 («записи заводит только
        # владелец») держит домен, но allauth должен слышать «нет» и от нас,
        # чтобы не завести запись в обход `pre_social_login`.
        return False

    def pre_social_login(self, request, sociallogin):
        account_id = request.user.pk if request.user.is_authenticated else None
        decision = identity.admit_external_login(
            identity_known=sociallogin.is_existing, account_id=account_id,
            policy_version=PRIVACY_POLICY_VERSION)
        if decision is ExternalLoginDecision.CONSENT_REQUIRED:
            raise ImmediateHttpResponse(redirect("oauth_connections"))
        if decision is ExternalLoginDecision.REJECTED:
            raise ImmediateHttpResponse(
                render(request, "billing/oauth_not_linked.html", status=403))
        # SIGN_IN и LINK: allauth продолжает своим путём — входит или привязывает.
