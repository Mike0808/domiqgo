from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider
from .views import ESIAOAuth2Adapter

class ESIAAccount(ProviderAccount):
    def to_str(self):
        return self.account.extra_data.get("oid") or super().to_str()

class ESIAProvider(OAuth2Provider):
    id = "esia"
    name = "Госуслуги"
    account_class = ESIAAccount
    oauth2_adapter_class = ESIAOAuth2Adapter

    def extract_uid(self, data):
        return str(data["oid"])

    def extract_common_fields(self, data):
        return {"username": data.get("oid", "")}

provider_classes = [ESIAProvider]
