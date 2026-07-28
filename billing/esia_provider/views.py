import base64
import json
from django.conf import settings
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter, OAuth2CallbackView, OAuth2LoginView,
)

def _decode_id_token_payload(id_token):
    """Decode the JWT payload WITHOUT verifying its signature.

    KNOWN LIMITATION: production use must verify against ESIA's published
    signing certificate before trusting this as authenticated identity —
    not implemented here. See
    docs/superpowers/specs/2026-07-27-oauth-login-design.md.
    """
    payload_b64 = id_token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))

class ESIAOAuth2Adapter(OAuth2Adapter):
    # Matches allauth's own YandexOAuth2Adapter convention: a plain string
    # rather than importing ESIAProvider here, so provider.py can import
    # this module to set oauth2_adapter_class without a circular import.
    provider_id = "esia"

    @property
    def authorize_url(self):
        return f"{settings.ESIA_BASE_URL}/aas/oauth2/ac"

    @property
    def access_token_url(self):
        return f"{settings.ESIA_BASE_URL}/aas/oauth2/te"

    def complete_login(self, request, app, token, **kwargs):
        id_token = kwargs.get("response", {}).get("id_token", "")
        claims = _decode_id_token_payload(id_token) if id_token else {}
        oid = claims.get("urn:esia:sbj_id") or claims.get("sub") or ""
        extra_data = {**claims, "oid": oid}
        return self.get_provider().sociallogin_from_response(request, extra_data)

oauth2_login = OAuth2LoginView.adapter_view(ESIAOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(ESIAOAuth2Adapter)
