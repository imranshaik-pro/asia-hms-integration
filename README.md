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

- **No submitted** Sales Invoice, payment, stock reservation or automatic stock mutation. Stage A can prepare only a visibly tax-pending draft (after batch review); batch review alone is not fulfillment.
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
- **No** GST/tax calculation, final payable amount, receipts (80mm/A4/PDF), or live health data deployment. An ASIA-linked draft cannot be submitted.
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

## Stage A — tax-pending invoice draft (not billing or dispensing)

This independent feature branch adds a narrowly scoped POST endpoint,
`asia_hms_integration.invoice_draft.prepare_invoice_draft(handoff_name, demo_acknowledged=1)`.
It is enabled only for the `ASIA Pharmacist` role after the handoff reaches
`Batch Data Reviewed`. The user must explicitly acknowledge the demo restrictions.

- Requires approved integration settings, matching clinic/pharmacy companies,
  a still-submitted source Patient Encounter, an enabled Patient-linked Customer,
  active pharmacy accounts, a single active leaf pharmacy Cost Center, an enabled
  INR `Standard Selling` Price List, unique active Item Prices and fresh
  Item/Batch/expiry/warehouse-stock checks.
- Creates exactly one `docstatus=0` Sales Invoice per handoff, linking it on
  the handoff together with creator/time and `Invoice Tax Review Pending` audit.
  Concurrent duplicate requests serialize on the handoff row lock, and retry
  returns the same draft. If the stored link is broken, drafting fails closed.
- Invoice contains reviewed Item/stock-UOM quantity, entered batch reference,
  configured pharmacy warehouse, pre-tax Item Price, valid income account and
  Cost Center, and Healthcare Patient/practitioner references.
- `update_stock=0`, `is_pos=0`, no tax rows, no paid amount and no advances.
  `remarks` labels the invoice **DEMO ONLY, TAX REVIEW PENDING, NOT FINAL**.
  Pricing is a *pre-tax estimate*, not a compliant total or payment request.
- Sales Invoice `validate` checks for unsafe changes to a linked draft and
  `before_submit` **always blocks** submission of an ASIA-linked invoice.
  Stage B is deliberately absent. No additional Create/Write Sales Invoice
  permission is granted to pharmacist accounts.

**Stage A is not safe for production** until independent Frappe v16 staging
integration tests verify native Sales Invoice validation, no GL/Stock Ledger
entries, no Serial and Batch Bundle movements, negative permission tests,
wrong batch/expiry, insufficient stock, price ambiguity/expiry, concurrent
requests, and submit rejection. The branch is *not deployed* by creating a PR.

### Staging acceptance sequence — administrator only

1. Back up the site and off-site copy, build and deploy a separate reviewed
   image tag, then run `bench --site frontend migrate` and `clear-cache`.
2. Check Handoff metadata and Sales Invoice hooks are loaded. Use a synthetic
   handoff with a submitted source Encounter and completed quantity/batch reviews.
3. Sign in with only `ASIA Pharmacist`, use **Prepare Draft Invoice (Tax Pending)**,
   acknowledge warnings, and verify the handoff links one Draft Sales Invoice
   with `invoice_tax_review_pending=1`, creator and timestamp.
4. Retry the API or button: confirm the existing invoice is reused and no second
   invoice exists. A pharmacist must not gain Sales Invoice Create/Write rights.
5. Check invoice has `docstatus=0`, `update_stock=0`, `is_pos=0`, empty taxes,
   zero paid/allocated amount, exact reviewed batch and quantity, and pricing
   marked tax pending. The amount is not final.
6. As an administrator, try to **submit the synthetic ASIA draft** and verify the
   Stage B disabled guard rejects it. Do not change the guard or force submission.
7. Independently compare Bin, Batch actual quantities, Stock Ledger Entry,
   General Ledger Entry, Payment Entry and reserve quantities with the baseline.
   All must remain unchanged from Stage A.
8. Repeat failure cases on separate synthetic records. Do not reuse production
   prescriptions and do not enable Stage B based on a green static CI check.

The Frappe-independent validators have unit tests, but these **do not substitute**
for real ERPNext integration acceptance on a backed-up staging site.
