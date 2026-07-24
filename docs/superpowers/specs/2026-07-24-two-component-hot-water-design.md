# Двухкомпонентный тариф ГВС — Design

**Date:** 2026-07-24
**Status:** Approved

## Problem

In Ufa, hot water (ГВС) is billed with two regulated components — «компонент на
холодную воду» (₽/м³) and «компонент на тепловую энергию» (₽/Гкал) — not a
single ₽/м³ rate. The apartment's meter measures only м³; the heat used to warm
the water is derived from a per-building norm (норматив расхода тепловой
энергии на подогрев, Гкал/м³). The current model has one `hot_water` tariff
type and cannot express this.

Formula: `cost = V × rate_ХВ + (V × norm) × rate_ТЭ`, where `V` is м³ consumed.

## Decisions (made with the landlord)

- Heat quantity comes **from the norm**, not a separate Гкал meter.
- The norm lives as a **field on Apartment** (`gvs_heat_norm`, Гкал/м³) — it
  depends on the building; tariff components depend on the region and are
  time-versioned.
- The receipt shows **two lines**, mirroring official Ufa payment documents.
- The old single `hot_water` tariff type is **replaced** (greenfield, no
  production data; no fallback path).

## Model changes

- `Tariff.UTILITY_CHOICES`: remove `hot_water`; add
  - `hot_water_cold_component` — «ГВС — компонент на холодную воду», ₽/м³
  - `hot_water_heat_component` — «ГВС — компонент на тепловую энергию», ₽/Гкал
  Both time-versioned via `effective_from` like all tariffs.
- `Apartment.gvs_heat_norm` — `DecimalField(max_digits=7, decimal_places=5,
  default=0)`, verbose name «Норматив подогрева ГВС, Гкал/м³», help text
  telling the landlord to take the value from the УК receipt
  («см. квитанцию УК»).

Schema migration only; no data migration (no production rows).

## Calculation core (`billing/services/calculation.py`, stays Django-free)

- `ApartmentConfig` gains `gvs_heat_norm: Decimal`.
- Meters unchanged: one `hot_water` meter in м³.
- When `has_hot_water`, emit two lines instead of one:
  1. code `hot_water_cold_component`, label «Горячая вода (компонент ХВ)»,
     quantity `V` м³, rate ₽/м³, amount `_money(V × rate)`.
  2. code `hot_water_heat_component`, label «Горячая вода (подогрев)»,
     quantity `V × gvs_heat_norm` Гкал (display quantized to 5 dp), rate
     ₽/Гкал, amount `_money(quantity × rate)`.
- Missing either component tariff raises the existing `MissingTariffError`
  (portal already maps it to «Тариф не настроен. Обратитесь к арендодателю.»).
- **Sewage unchanged**: `(cold V + hot V) × sewage rate` — водоотведение is
  volume-based; heat does not enter it.

## ORM glue (`billing/services/statements.py`)

- `_tariffs_for()` requests the two new types for hot-water apartments.
- The `ApartmentConfig` construction passes `apartment.gvs_heat_norm`.
- `line_to_dict` unchanged (already serializes arbitrary quantity/rate).
- Existing admin `regenerate_statements` action recomputes old periods once
  the component tariffs are entered — no new admin work.

## Out of scope

- Separate Гкал meters for ГВС (no such hardware in these apartments).
- Norm versioning over time (norm changes are rare; landlord edits the field,
  and past statements are only altered by explicit regeneration).
- Any change to cold water, electricity, internet, rent lines.

## Testing

- Calculation: two-line ГВС math against a hand-computed example with
  ROUND_HALF_UP boundary; sewage still uses м³ volumes; missing either
  component → `MissingTariffError`; `gvs_heat_norm = 0` yields a zero-amount
  подогрев line (valid: norm not yet entered).
- Statements service: tariff selection picks the latest effective components.
- Portal end-to-end: submit readings, statement contains both ГВС lines and
  correct total.
- Update existing tests that used the removed `hot_water` type.
