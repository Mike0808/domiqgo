import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("boss", "b@e.com", "pass12345")
    c = Client()
    c.login(username="boss", password="pass12345")
    return c
