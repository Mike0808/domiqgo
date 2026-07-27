from decimal import Decimal
from django import forms

class MeterReadingForm(forms.Form):
    """Dynamic form: one DecimalField per meter this apartment uses.

    `serials` maps meter code -> заводской номер; when present, the number is
    appended to the label so the tenant knows which physical device to read.
    """
    def __init__(self, *args, meters=None, serials=None, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "cold_water": "Холодная вода (м³)",
            "hot_water": "Горячая вода (м³)",
            "electricity_single": "Электроэнергия (кВт·ч)",
            "electricity_day": "Электроэнергия день (кВт·ч)",
            "electricity_night": "Электроэнергия ночь (кВт·ч)",
        }
        serials = serials or {}
        for meter in (meters or []):
            label = labels[meter]
            if serials.get(meter):
                label = f"{label} — счётчик № {serials[meter]}"
            self.fields[meter] = forms.DecimalField(
                label=label, min_value=Decimal("0"), max_digits=12, decimal_places=3)

class ConsentForm(forms.Form):
    consent = forms.BooleanField(
        label="Я ознакомлен(а) и даю согласие на обработку персональных данных.",
        required=True)
