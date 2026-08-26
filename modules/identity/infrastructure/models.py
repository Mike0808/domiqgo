"""Хранение согласий. Единственное место модуля, знающее о базе.

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
