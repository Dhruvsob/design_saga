"""Every collection that holds a tenant's own records (keyed by `org_id`).

Tenant export and purge both read this list, and a test fails when code starts
using a scoped collection that is not registered here, so a new module can't
leave a deleted customer's data behind.
"""

TENANT_COLLECTIONS = (
    # People and access
    "users", "user_app_locks", "user_invites", "role_permissions", "user_favorite_accounts",
    "ai_usage",
    "employees", "employee_advances", "time_entries",
    "attendance", "attendance_corrections", "attendance_policies", "office_locations",
    "leave_applications", "leave_rules", "leaves", "holidays", "payroll_runs",
    # Sales and projects
    "leads", "clients", "quotations", "quotations_adv",
    "projects", "project_phases", "tasks", "milestones", "payment_milestones",
    "drawings", "snags", "site_visits", "files", "documents", "comments",
    "chat_messages", "ai_messages", "calendar_events",
    # Vendors and procurement
    "vendors", "vendors_acc", "vendor_bills", "vendor_payments", "vendor_commissions",
    "vendor_ratings", "commission_settlements", "purchase_orders", "goods_receipts",
    # Money
    "invoices", "payment_reminders", "reminder_alerts",
    "collection_receivables", "collection_receipts",
    "journal_entries", "accounts", "period_closes", "period_exports",
    "bank_statement_rows", "bank_statement_batches",
    "expenses", "expense_policies", "expense_receipts", "recurring_expenses", "loans",
    # Settings, notifications and integrations
    "master_data", "counters", "notifications", "audit_log",
    "google_calendar_connections", "google_oauth_states",
    "google_calendar_sync_queue", "google_calendar_synced_events",
)

# Integration state with credentials or one-time secrets: purged, never exported
# (a customer reconnects Google in their new system).
EXPORT_SKIPPED = frozenset({
    "user_invites",
    "google_calendar_connections", "google_oauth_states",
    "google_calendar_sync_queue", "google_calendar_synced_events",
})

# Secrets removed from exported rows.
EXPORT_REDACTED_FIELDS = {
    "users": ("password_hash",),
    "user_app_locks": ("pin_hash",),
}
