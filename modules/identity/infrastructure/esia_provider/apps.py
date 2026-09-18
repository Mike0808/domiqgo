from allauth.socialaccount.apps import SocialAccountConfig

class ESIAProviderConfig(SocialAccountConfig):
    # Инфраструктура Identity (шаг H1 расформирования): способ поговорить с
    # конкретным провайдером — allauth-адаптер Госуслуг. Метка прежняя:
    # моделей у приложения нет, менять нечего.
    name = "modules.identity.infrastructure.esia_provider"

    def ready(self):
        super().ready()
        from allauth.socialaccount.providers import registry
        from .provider import ESIAProvider
        registry.register(ESIAProvider)
