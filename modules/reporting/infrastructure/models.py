"""Журнал выгрузок. Единственная таблица модуля.

Аудит по 152-ФЗ, а не история для удобства: запись не изменяется и не
удаляется, у неё нет ни формы правки, ни кнопки удаления.
"""

from django.db import models


class ExportRun(models.Model):
    STATES = [("started", "Начата"), ("succeeded", "Выполнена"),
              ("failed", "Не удалась")]

    report_code = models.CharField("Отчёт", max_length=20)
    initiated_by = models.PositiveIntegerField("Инициатор")
    scope = models.CharField("Область", max_length=200)
    state = models.CharField("Исход", max_length=10, choices=STATES,
                             default="started")
    error = models.CharField("Ошибка", max_length=300, blank=True)
    started_at = models.DateTimeField("Начата", auto_now_add=True)

    class Meta:
        db_table = "reporting_export_run"
        verbose_name = "Выгрузка"
        verbose_name_plural = "Журнал выгрузок"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.report_code} · {self.get_state_display()} · #{self.initiated_by}"
