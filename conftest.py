import pytest

@pytest.fixture(autouse=True)
def _non_manifest_static_storage(settings):
    """Tests render admin pages via {% static %}; avoid requiring a built
    manifest (production keeps WhiteNoise's ManifestStaticFilesStorage)."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
