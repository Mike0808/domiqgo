from decimal import Decimal
from django import forms

class MeterReadingForm(forms.Form):
    """Dynamic form: one DecimalField per meter this apartment uses."""
    def __init__(self, *args, meters=None, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "cold_water": "Холодная вода (м³)",
            "hot_water": "Горячая вода (м³)",
            "electricity_single": "Электроэнергия (кВт·ч)",
            "electricity_day": "Электроэнергия день (кВт·ч)",
            "electricity_night": "Электроэнергия ночь (кВт·ч)",
        }
        for meter in (meters or []):
            self.fields[meter] = forms.DecimalField(
                label=labels[meter], min_value=Decimal("0"), max_digits=12, decimal_places=3)
