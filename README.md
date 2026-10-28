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
- Allows role **ASIA Pharmacist** to read the pharmacy queue and confirm **stock-UOM quantities**
  through a narrowly scoped, POST-only review action. The original clinical prescription and
  read-only DocType permissions are preserved. A recorded reviewer, timestamp, and note are
  visible on the handoff; status becomes **Quantity Reviewed**, not **Dispensed**.
- After quantity review, allows a **demo-only batch data review**: the pharmacist types one batch number and fictional pack expiry per medicine line; the server matches both against ERPNext, rejects disabled/expired batches and insufficient batch or unreserved warehouse stock, and audits the reviewer, time, and note. The handoff becomes **Batch Data Reviewed**, never Dispensed.
- If a submitted encounter is cancelled, marks the pending handoff cancelled, or flags processed
  ones **Review Required** for human reconciliation.
- Requires a configured clinic company, pharmacy company, retail warehouse, and an admin's
  acknowledgement that the clinic–pharmacy data sharing policy is approved.

## What it deliberately does NOT do yet

- **No** Sales Invoice, payment, stock reservation or automatic stock mutation. Batch review is a comparison, not fulfillment.
- Quantity confirmation checks unreserved Bin stock but **does not reserve any**.
- Batch data review compares manually entered batch/expiry with the ERPNext Batch record and
  point-in-time batch + unreserved Bin stock. It cannot independently establish that a real
  package was physically inspected or prove the accuracy of a typed expiry, and does **not**
  authorize billing or dispensing, even after a match.
- **No** dispensing, substitution, controlled-drug compliance, prescription validity or
  partial-dispensing reconciliation.
- **No** strip/loose-unit UOM conversion yet.
- **No** reservation-aware, batch-level allocation or batch split across multiple lots.
  ERPNext **Bin** reports warehouse totals; a point-in-time batch quantity check does not
  reserve inventory and cannot prevent another transaction consuming it. Final fulfillment
  must recheck batch, expiry, stock, patient/Rx and permissions atomically.
- Stock search results remain labelled **not batch/expiry verified**. Pharmacist must
  independently inspect the real package, original Rx, and local dispensing requirements.
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
- `asia_hms_integration.api.pharmacy_queue(limit=20)`: unfulfilled handoffs for pharmacy role.
- `asia_hms_integration.review.confirm_quantities(handoff_name, quantities, review_note)`:
  POST-only, ASIA Pharmacist-only, checks all child-row quantities, stock and source Encounter;
  records a non-dispensing quantity review. It never approves a sale or validates batch/expiry.
- `asia_hms_integration.batch_review.review_batch_data(handoff_name, reviews, review_note, demo_acknowledged=1)`:
  POST-only, ASIA Pharmacist-only; requires completed quantity review, explicit demo
  acknowledgement, every medicine line with manually typed batch and expiry, active tracked
  Items/Batches, exact ERPNext expiry match, unexpired batches, enough per-batch stock and
  unreserved total warehouse stock. Records the audit trail and **Batch Data Reviewed** only.
  Returns `batch_data_matched: true`, `batch_expiry_verified: false`,
  `dispensing_authorized: false`, `stock_reserved: false`.

Response includes warehouse, actual quantity, reserved quantity, available quantity and
`batch_expiry_verified: false`. No stock changes from these endpoints.

## Data ownership

- Clinical source: Marley Healthcare `Patient Encounter` and `Drug Prescription`.
- Stock source: ERPNext `Item`, `Warehouse`, `Bin`, `Batch` and batch quantity API.
- Pharmacy queue: `ASIA Rx Handoff` and child `ASIA Rx Item`; one source encounter is unique.
- Config: `ASIA Integration Settings` (Single DocType).

## Local verification

Static CI checks Python syntax and validates DocType JSON on push / pull request.
It **does not** prove Frappe migrations, patient access controls, UI or billing work.
Those require a dedicated v16 staging site and end-to-end tests before actual use.


## Demo batch data review — staging acceptance

1. Upgrade the **staging image** in a separate reviewed deployment only after taking a
   current backup. Run `bench --site frontend migrate` and `bench --site frontend clear-cache`.
2. Sign in as the dedicated **ASIA Pharmacist**, open a **Quantity Reviewed** handoff,
   select **Review Batch & Expiry (Demo Only)**, and type the fictional pack's batch ID and
   expiry. For the current synthetic example: `ST251131`, `2027-05-31`.
3. Enter an audit note acknowledging no physical validation, tick the demo-only warning,
   and save. Check the status is **Batch Data Reviewed**, the row records batch/expiry,
   and the recorded reviewer, timestamp and note match the logged-in pharmacist.
4. In independent staging test records, confirm wrong expiry, wrong-item batch, expired
   or disabled batch, insufficient per-batch stock, missing medicine row, cancelled source
   encounter, unauthorized user, and repeat submission all fail closed.
5. Check stock `Bin`, serial/batch ledger, and Sales Invoice remain unchanged after review.
   **Do not create or submit a Sales Invoice or dispense anything in this step.**

The ERPNext Batch quantity API may require **Batch Select** access for the pharmacist.
If a role permission error occurs, have an administrator evaluate and grant only the
necessary least-privilege permission in staging; do not replace the check with an
unrestricted quantity lookup.
