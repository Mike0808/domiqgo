"""Хранение согласий и кодов привязки. Единственное место модуля, знающее о базе.

Ссылка на учётную запись — идентификатором без констрейнта (правило 1.3).
Учётной записью на P1 служит `auth.User` Django: заводить собственную таблицу
пользователей ради переименования значило бы переписать вход, сессии и
админку разом, ничего не выиграв. Identity владеет тем, чего у `auth.User`
нет: журналом согласий, кодом привязки и правилами входа.
"""

from django.db import models


class Consent(models.Model):
    """Один акт согласия на обработку персональных данных.

    Строка на каждое согласие, а не поле на учётной записи: для 152-ФЗ
    доказательством служит факт согласия на конкретную редакцию в конкретный
    момент. Прежние записи не изменяются и не удаляются никогда.
    """

    account_id = models.PositiveIntegerField("Учётная запись", db_index=True)
    policy_version = models.CharField("Редакция политики", max_length=32)
    given_at = models.DateTimeField("Дано")

    class Meta:
        db_table = "identity_consent"
        verbose_name = "Согласие на обработку ПДн"
        verbose_name_plural = "Согласия на обработку ПДн"
        ordering = ["given_at"]

    def __str__(self):
        return f"#{self.account_id}: {self.policy_version} от {self.given_at:%d.%m.%Y}"


class LinkCode(models.Model):
    """Действующий код привязки учётной записи.

    Строка существует, пока код действует: погашение — удаление строки, а не
    флаг. Одна строка на запись (`unique`) — выпуск нового кода замещает
    прежний; код уникален, потому что по нему ищут владельца.
    """

    account_id = models.PositiveIntegerField("Учётная запись", unique=True)
    code = models.CharField("Код", max_length=32, unique=True)

    class Meta:
        db_table = "identity_link_code"
        verbose_name = "Код привязки"
        verbose_name_plural = "Коды привязки"

    def __str__(self):
        return f"#{self.account_id}: {self.code}"


class Account(models.Model):
    """Реестр учётных записей: тип поверх `auth.User`.

    Строка есть не у каждой записи: реестр заполнила миграция C4e, а новые
    записи заводятся стандартной админкой Django, которая о реестре не знает.
    Незарегистрированной записи тип назначается мостом от флага «персонал»
    (`domain.type_from_staff_flag`) — до появления `CreateAccount` в панели.
    """

    OWNER = "owner"
    TENANT = "tenant"
    TYPE_CHOICES = [(OWNER, "Владелец"), (TENANT, "Жилец")]

    account_id = models.PositiveIntegerField("Учётная запись", unique=True)
    type = models.CharField("Тип", max_length=10, choices=TYPE_CHOICES)

    class Meta:
        db_table = "identity_account"
        verbose_name = "Учётная запись"
        verbose_name_plural = "Учётные записи"

    def __str__(self):
        return f"#{self.account_id}: {self.get_type_display()}"
