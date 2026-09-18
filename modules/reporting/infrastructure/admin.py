"""Журнал выгрузок и запуск отчётов — раздел владельца.

Право запрашивающего проверяет прикладной слой (ADR-0023): сюда попадает
только персонал админки, и его учётная запись пишется в журнал инициатором.
Запись журнала не правится и не удаляется (инвариант 2) — руками тоже.
"""

from datetime import date

from django.contrib import admin
from django.http import HttpResponse

from .. import api
from .models import ExportRun

XLSX_TYPE = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")


@admin.register(ExportRun)
class ExportRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "report_code", "initiated_by", "scope",
                    "state", "error")
    list_filter = ("report_code", "state")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Кнопки отчётов живут над журналом: выгрузка и её след — одно
        место. `?run=<код>` запускает отчёт и отдаёт файл, не сохраняя его
        (инвариант 4)."""
        code = request.GET.get("run")
        if code:
            params, scope = {}, "все объекты"
            bounds = []
            for key in ("from", "to"):
                raw = request.GET.get(key)
                if raw:
                    year, month = raw.split("-")
                    params[key] = date(int(year), int(month), 1)
                    bounds.append(raw)
            if bounds:
                scope = "период " + "..".join(bounds)
            filename, payload = api.run_export(code, request.user.pk,
                                               scope=scope, params=params)
            response = HttpResponse(payload, content_type=XLSX_TYPE)
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        return super().changelist_view(request, extra_context)
