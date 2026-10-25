from routes.notifications import notification_owner_filter


def test_notification_owner_filter_requires_current_tenant_and_user():
    user = {"user_id": "user_a", "org_id": "org_current"}

    assert notification_owner_filter(user) == {
        "user_id": "user_a",
        "org_id": "org_current",
    }
    assert notification_owner_filter(user, id="ntf_1", read=False) == {
        "user_id": "user_a",
        "org_id": "org_current",
        "id": "ntf_1",
        "read": False,
    }


def test_notification_owner_filter_uses_effective_impersonated_tenant():
    user = {
        "user_id": "superadmin",
        "role": "SuperAdmin",
        "is_super_admin": True,
        # apply_session_context places the selected tenant in org_id for only
        # the current Super Admin session.
        "org_id": "org_selected",
        "impersonating": True,
    }

    assert notification_owner_filter(user)["org_id"] == "org_selected"
