"""JSON-вид: типы честнее XLSX — за это его и выбирают (спецификация)."""

import json
from datetime import date, datetime
from decimal import Decimal


def dumps(payload) -> bytes:
    def encode(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(type(value).__name__)

    return json.dumps(payload, default=encode, ensure_ascii=False,
                      indent=2).encode("utf-8")
