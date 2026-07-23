def test_settings_locale():
    from django.conf import settings
    assert settings.LANGUAGE_CODE == "ru"
    assert settings.TIME_ZONE == "Asia/Yekaterinburg"
