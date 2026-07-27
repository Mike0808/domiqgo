from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.static import serve
from allauth.socialaccount.models import SocialAccount
from .consent import PRIVACY_POLICY_VERSION
from .forms import MeterReadingForm
from .models import Document, MeterReading, MonthlyStatement, Tenant
from .services.calculation import MissingTariffError
from .services.statements import MissingBaselineError, meters_for, generate_statement

def _current_period():
    return timezone.localdate().replace(day=1)

def _tenant_for(request):
    try:
        return request.user.tenant
    except Tenant.DoesNotExist:
        return None

def _no_tenant_response(request):
    if request.user.is_staff:
        return redirect("/admin/")
    return render(request, "billing/no_tenant.html")

@login_required
def current_month(request):
    tenant = _tenant_for(request)
    if tenant is None:
        return _no_tenant_response(request)
    apartment = tenant.apartment
    meters = meters_for(apartment)
    serials = {m.kind: m.serial_number for m in apartment.meters.all()}
    period = _current_period()
    statement = MonthlyStatement.objects.filter(apartment=apartment, period=period).first()
    locked = statement is not None and statement.status in (MonthlyStatement.PAID, MonthlyStatement.PENDING)

    if request.method == "POST":
        if locked:
            messages.error(request, "Показания заблокированы: месяц оплачен или платёж на проверке.")
            return redirect("current_month")
        form = MeterReadingForm(request.POST, meters=meters, serials=serials)
        if form.is_valid():
            existing = {r.meter: r for r in
                        MeterReading.objects.filter(apartment=apartment, period=period)}
            try:
                with transaction.atomic():
                    for meter in meters:
                        value = form.cleaned_data[meter]
                        obj = existing.get(meter)
                        if obj:
                            obj.value = value
                            obj.entered_by_tenant = True
                            obj.save()
                        else:
                            MeterReading.objects.create(
                                apartment=apartment, period=period, meter=meter,
                                value=value, entered_by_tenant=True)
                    generate_statement(apartment, period)
            except ValueError as exc:
                messages.error(request, f"Ошибка: показание уменьшилось. {exc}")
                return render(request, "billing/current_month.html",
                              {"form": form, "statement": None, "period": period,
                               "locked": False})
            except MissingTariffError:
                messages.error(request, "Тариф не настроен. Обратитесь к арендодателю.")
                return render(request, "billing/current_month.html",
                              {"form": form, "statement": None, "period": period,
                               "locked": False})
            except MissingBaselineError:
                messages.error(
                    request, "Начальные показания не заданы. Обратитесь к арендодателю.")
                return render(request, "billing/current_month.html",
                              {"form": form, "statement": None, "period": period,
                               "locked": False})
            messages.success(request, "Показания сохранены.")
            return redirect("current_month")
    else:
        entered = {r.meter: r.value for r in
                   MeterReading.objects.filter(apartment=apartment, period=period)}
        form = MeterReadingForm(meters=meters, serials=serials, initial=entered)

    return render(request, "billing/current_month.html",
                  {"form": form, "statement": statement, "period": period,
                   "locked": locked})

@login_required
def history(request):
    tenant = _tenant_for(request)
    if tenant is None:
        return _no_tenant_response(request)
    statements = MonthlyStatement.objects.filter(apartment=tenant.apartment).order_by("-period")
    return render(request, "billing/history.html", {"statements": statements})

@login_required
def documents(request):
    tenant = _tenant_for(request)
    if tenant is None:
        return _no_tenant_response(request)
    docs = tenant.documents.all()
    return render(request, "billing/documents.html", {"documents": docs})

@login_required
def media_file(request, path):
    """Serve an uploaded file only to its owner (or staff).

    All /media URLs route here — nothing under MEDIA_ROOT is ever served
    without authentication (rental agreements contain passport data).
    """
    if not request.user.is_staff and not Document.objects.filter(
            file=path, tenant__user=request.user).exists():
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)

@login_required
def oauth_connections(request):
    tenant = _tenant_for(request)
    if tenant is None:
        return _no_tenant_response(request)
    if request.method == "POST" and "consent" in request.POST:
        tenant.privacy_consent_at = timezone.now()
        tenant.privacy_consent_version = PRIVACY_POLICY_VERSION
        tenant.save(update_fields=["privacy_consent_at", "privacy_consent_version"])
        return redirect("oauth_connections")
    if tenant.privacy_consent_version != PRIVACY_POLICY_VERSION:
        return render(request, "billing/oauth_consent.html", {})
    connected_provider_ids = list(
        SocialAccount.objects.filter(user=request.user).values_list("provider", flat=True))
    return render(request, "billing/oauth_connections.html",
                  {"connected_provider_ids": connected_provider_ids})

def privacy_policy(request):
    return render(request, "billing/privacy_policy.html", {})
