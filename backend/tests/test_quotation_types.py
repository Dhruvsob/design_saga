"""Regression coverage for the two supported commercial quotation types."""

import pytest
from pydantic import ValidationError

import server


def test_only_consultancy_and_turnkey_can_be_created():
    assert server.QUOTATION_TYPES == ["turnkey", "consultancy"]
    assert server.QuotationCreate(
        type="consultancy", project_title="Krunal Soni Residence",
    ).type == "consultancy"
    with pytest.raises(ValidationError):
        server.QuotationCreate(type="execution", project_title="Legacy type")
    with pytest.raises(ValidationError):
        server.QuotationCreate(type="hybrid", project_title="Legacy type")


def test_consultancy_defaults_use_consultancy_terms_and_schedule():
    doc = server._new_quotation_doc(
        {"type": "consultancy", "project_title": "Krunal Soni Residence"},
        {"user_id": "admin", "name": "Admin"},
    )
    assert doc["type"] == "consultancy"
    assert doc["terms"] == server.CONSULTANCY_TERMS
    assert [row["label"] for row in doc["payment_plan"]] == [
        row["label"] for row in server.DEFAULT_PAYMENT_PLAN_BY_TYPE["consultancy"]
    ]
    assert sum(row["percentage"] for row in doc["payment_plan"]) == 100


def test_legacy_templates_remain_available_for_historical_records():
    assert "execution" in server.DEFAULT_PAYMENT_PLAN_BY_TYPE
    assert "hybrid" in server.DEFAULT_PAYMENT_PLAN_BY_TYPE
