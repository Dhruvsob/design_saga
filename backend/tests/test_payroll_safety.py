"""Focused regression coverage for payroll payment safety."""

from routes import payroll


def test_payroll_period_key_is_stable_and_period_specific():
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) == "org_a:emp_a:2026-09"
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_a", "emp_a", 2026, 10)
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_a", "emp_b", 2026, 9)
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_b", "emp_a", 2026, 9)
