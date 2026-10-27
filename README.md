# ASIA HMS Integration

An initial, reviewable Frappe v16 application connecting **Dr. Sara Cardio Care & Polyclinic**
with **Health Cube Pharmacy** on one ERPNext + [Marley Healthcare](https://github.com/earthians/marley) site.

> **Development MVP, not approved for live patient use.** Requires formal clinical, security,
> legal/privacy and pharmacy workflow validation, plus site backup and restore testing.

## What this first iteration does

- Role-gated, live stock lookup in Health Cube Pharmacy's **configured retail warehouse**, for
  physicians using Marley's **Patient Encounter** form.
- Search medicines by Item code or name via authenticated API; the Encounter's **ASIA HMS →
  Check Health Cube Stock** button refreshes quantities on demand.
- Creates one **ASIA Rx Handoff** queue record when an outpatient **Patient Encounter is
  submitted** (not while it is a draft), after an admin explicitly enables sharing.
- Stores only minimal patient identification and prescription medicine rows, not diagnosis or
  the entire chart.
- Allows role **ASIA Pharmacist** to read the pharmacy queue, but not edit clinical source
  prescriptions or automatically dispense.
- If a submitted encounter is cancelled, marks the pending handoff cancelled, or flags processed
  ones **Review Required** for human reconciliation.
- Requires a configured clinic company, pharmacy company, retail warehouse, and an admin's
  acknowledgement that the clinic–pharmacy data sharing policy is approved.

## What it deliberately does NOT do yet

- **No** Sales Invoice, payment, batch selection, stock reservation or automatic stock mutation.
- **No** dispensing, substitution, controlled-drug compliance, prescription validity or
  partial-dispensing reconciliation.
- **No** strip/loose-unit UOM conversion yet.
- **No** batch/expiry-aware available-to-dispense calculation: ERPNext **Bin** reports a
  current warehouse quantity, not a clinically or legally validated dispensable quantity.
  Every result is labelled **not batch/expiry verified**; pharmacist must independently check.
- **No** GST/tax calculation, receipts (80mm/A4/PDF), or live health data deployment.
- **No** support for inpatient medication orders.

## Compatibility

Intended for Frappe 16, ERPNext 16, Marley app `healthcare` 16.6.x.
Reference app image: `ghcr.io/imranshaik-pro/asia-hms:16-marley`.
This branch is **not included** in that image until the build pipeline is explicitly changed.

## Deployment plan (ONLY on a backed-up staging site)

1. Recover and verify old Frappe site backup and configuration first; **do not replace** the
   existing Frappe database or use `docker compose down -v`.
2. Add this repository to Docker image's `apps.json` in a reviewed PR and build a **new image tag**.
3. Run staging `bench --site frontend install-app asia_hms_integration` using the new image.
4. Set the existing Company records, pharmacy warehouse, and optional Item Group in
   **ASIA Integration Settings**. Keep `enabled=0` until roles and policy review are complete.
5. Grant `Physician` only to authorized doctors, `ASIA Pharmacist` only to dispensing staff,
   and restrict `System Manager` accounts. Do **not** use a shared login.
6. Test submitted/draft/cancelled encounters, missing/empty stock, duplicate submit,
   an out-of-stock Rx, and access-denied requests using **synthetic patients**.
7. Develop/verify pharmacist billing, batch-expiry and returns integration in separate PRs.

## API (authenticated Frappe RPC)

- `asia_hms_integration.api.search_medicines(query="par")`: up to 20 stock Item matches.
- `asia_hms_integration.api.stock_for_items(item_codes='["ITEM-001"]')`: refresh up to 30 Items.
- `asia_hms_integration.api.pharmacy_queue(limit=20)`: pending/review handoffs for pharmacy role.

Response includes warehouse, actual quantity, reserved quantity, available quantity and
`batch_expiry_verified: false`. No stock changes from these endpoints.

## Data ownership

- Clinical source: Marley Healthcare `Patient Encounter` and `Drug Prescription`.
- Stock source: ERPNext `Item`, `Warehouse`, `Bin`.
- Pharmacy queue: `ASIA Rx Handoff` and child `ASIA Rx Item`; one source encounter is unique.
- Config: `ASIA Integration Settings` (Single DocType).

## Local verification

Static CI checks Python syntax and validates DocType JSON on push / pull request.
It **does not** prove Frappe migrations, patient access controls, UI or billing work.
Those require a dedicated v16 staging site and end-to-end tests before actual use.
