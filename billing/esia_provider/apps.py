from allauth.socialaccount.apps import SocialAccountConfig

class ESIAProviderConfig(SocialAccountConfig):
    name = "billing.esia_provider"

    def ready(self):
        super().ready()
        from allauth.socialaccount.providers import registry
        from .provider import ESIAProvider
        registry.register(ESIAProvider)
