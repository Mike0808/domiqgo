import base64
import json
from billing.esia_provider.provider import ESIAProvider
from billing.esia_provider.views import ESIAOAuth2Adapter, _decode_id_token_payload

def test_esia_provider_registered_with_id():
    assert ESIAProvider.id == "esia"
    assert ESIAProvider.name == "Госуслуги"

def test_decode_id_token_payload_reads_claims_without_verifying_signature():
    payload = {"sub": "1000000001", "urn:esia:sbj_id": "1000000001"}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_jwt = f"headerpart.{payload_b64}.signaturepart"
    claims = _decode_id_token_payload(fake_jwt)
    assert claims["sub"] == "1000000001"

def test_authorize_and_token_urls_use_esia_base_url(settings):
    settings.ESIA_BASE_URL = "https://esia-portal1.test.gosuslugi.ru"
    adapter = ESIAOAuth2Adapter(request=None)
    assert adapter.authorize_url == "https://esia-portal1.test.gosuslugi.ru/aas/oauth2/ac"
    assert adapter.access_token_url == "https://esia-portal1.test.gosuslugi.ru/aas/oauth2/te"
