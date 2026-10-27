"""Integration hooks for one-site Frappe/ERPNext/Marley Healthcare v16."""

app_name = "asia_hms_integration"
app_title = "ASIA HMS Integration"
app_publisher = "ASIA HMS Team"
app_description = "Clinic and pharmacy handoff with live pharmacy stock lookup"
app_email = "support@example.invalid"
app_license = "MIT"

# The installed Frappe app is named healthcare (repository: earthians/marley).
required_apps = ["erpnext", "healthcare"]

before_install = "asia_hms_integration.setup.before_install"
after_install = "asia_hms_integration.setup.after_install"
after_migrate = "asia_hms_integration.setup.after_migrate"

doc_events = {
    "Patient Encounter": {
        "on_submit": "asia_hms_integration.handoff.on_encounter_submit",
        "on_cancel": "asia_hms_integration.handoff.on_encounter_cancel",
    }
}

doctype_js = {
    "Patient Encounter": "public/js/patient_encounter.js",
}
