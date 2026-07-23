from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import MeterReadingForm
from .models import MeterReading, MonthlyStatement
from .services.statements import meters_for, generate_statement

def _current_period():
    return timezone.localdate().replace(day=1)

@login_required
def current_month(request):
    tenant = request.user.tenant
    apartment = tenant.apartment
    meters = meters_for(apartment)
    period = _current_period()

    if request.method == "POST":
        form = MeterReadingForm(request.POST, meters=meters)
        if form.is_valid():
            existing = {r.meter: r for r in
                        MeterReading.objects.filter(apartment=apartment, period=period)}
            # Save then attempt to generate; roll back the save if the math rejects it.
            saved = []
            for meter in meters:
                value = form.cleaned_data[meter]
                obj = existing.get(meter)
                if obj:
                    obj.value = value; obj.entered_by_tenant = True; obj.save()
                else:
                    obj = MeterReading.objects.create(
                        apartment=apartment, period=period, meter=meter,
                        value=value, entered_by_tenant=True)
                saved.append(obj)
            try:
                generate_statement(apartment, period)
            except ValueError as exc:
                for obj in saved:
                    obj.delete()
                messages.error(request, f"Ошибка: показание уменьшилось. {exc}")
                return render(request, "billing/current_month.html",
                              {"form": form, "statement": None, "period": period})
            messages.success(request, "Показания сохранены.")
            return redirect("current_month")
    else:
        form = MeterReadingForm(meters=meters)

    statement = MonthlyStatement.objects.filter(apartment=apartment, period=period).first()
    return render(request, "billing/current_month.html",
                  {"form": form, "statement": statement, "period": period})

@login_required
def history(request):
    apartment = request.user.tenant.apartment
    statements = MonthlyStatement.objects.filter(apartment=apartment).order_by("-period")
    return render(request, "billing/history.html", {"statements": statements})

@login_required
def documents(request):
    docs = request.user.tenant.documents.all()
    return render(request, "billing/documents.html", {"documents": docs})
