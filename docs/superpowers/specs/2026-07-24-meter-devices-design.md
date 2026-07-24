# Счётчики с начальными показаниями из договора — Design

**Date:** 2026-07-24
**Status:** Approved

## Problem

Consumption needs a baseline. Today the baseline is "whatever readings exist
for an earlier month", entered by the landlord as raw `MeterReading` rows with
free-text meter names. Two failures follow: a mistyped meter name is silently
ignored, and a missing baseline silently bills the meter's absolute value
(previous defaults to 0). The real-world anchor — meter values fixed in the
акт at contract signing — has no home in the model.

## Decisions (made with the landlord)

- Monthly consumption = current − previous month; the **first** month uses the
  contract-fixed initial value. (Standard ЖКХ; not cumulative-from-contract.)
- Meters are modeled as entities with a заводской номер and initial value.

## Model

New `Meter` («Счётчик»), edited inline on the apartment admin page:

- `apartment` FK → Apartment, related_name `meters`
- `kind` — choices shared constant `METER_KIND_CHOICES`: `cold_water`,
  `hot_water`, `electricity_single`, `electricity_day`, `electricity_night`
- `serial_number` — «Заводской номер», blank allowed
- `initial_value` — «Начальное показание» (Decimal 12,3, same scale as readings)
- `initial_date` — «Дата фиксации» (contract signing), optional
- `unique_together (apartment, kind)`; meter replacement/поверка out of scope.

`MeterReading.meter` gains the same choices (dropdown in admin; existing rows
use exactly these codes already).

## Baseline logic (`billing/services/statements.py`)

`_previous_readings` becomes per-meter:

1. latest `MeterReading` for that meter with `period < current` → use it;
2. else the apartment's `Meter.initial_value` for that kind → use it;
3. else collect as missing; any missing meter ⇒ raise `MissingBaselineError`.

This removes the silent bill-from-0 path and the partial-prior-period
inflation bug (baseline is now assembled per meter, not from a single period).

The portal maps `MissingBaselineError` to «Начальные показания не заданы.
Обратитесь к арендодателю.» (same pattern as `MissingTariffError`).

## Tenant form

Field labels include the device number when known:
«Холодная вода (м³) — счётчик № 123456». No other portal changes.

## Admin

- `MeterInline` on Apartment («Счётчики»): kind, serial, initial value/date.
- `MeterReadingAdmin.save_model` regenerates that month's statement after
  saving a reading (warning message if recalculation fails, e.g. no tariff).

## Out of scope

- Meter replacement / поверка history.
- Cumulative «всего с заселения» column (possible later from initial values).

## Testing

- Baseline from initial values on first month; mixed per-meter fallback
  (one meter has a prior reading, another falls back to initial).
- MissingBaselineError raised without meter/initial; portal shows the message.
- Serial number appears in the form label.
- Admin reading save regenerates the statement; meter field is a dropdown.
- Existing tests updated: generation without baselines now requires explicit
  Meter rows (initial 0 where absolute billing was the intent).
