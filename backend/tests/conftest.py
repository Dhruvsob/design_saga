"""Shared test setup.

Gates read the plan catalogue through ``core.entitlements.load_plans``. Unit
tests use fake databases, so they get the built-in default catalogue instead
of a real read (a cached real read would also outlive each test's event loop).
Tests of the catalogue itself patch ``load_plans`` explicitly.
"""
import copy

import pytest

import core.entitlements as entitlements


@pytest.fixture(autouse=True)
def _default_plan_catalogue(monkeypatch):
    async def load_plans():
        return copy.deepcopy(entitlements.DEFAULT_PLANS)

    monkeypatch.setattr(entitlements, "load_plans", load_plans)
    entitlements.invalidate_plans()
