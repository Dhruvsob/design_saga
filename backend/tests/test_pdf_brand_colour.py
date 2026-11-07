"""PDFs use the brand taupe unless the studio picked its own colour (Phase 1.1)."""
from core.pdf_brand import BRAND_PRIMARY, Brand, brand_primary_hex, hex_to_rgb


def test_old_blue_default_and_empty_mean_brand_taupe():
    assert brand_primary_hex({"primary_color": "#002FA7"}) == BRAND_PRIMARY
    assert brand_primary_hex({"primary_color": "#002fa7"}) == BRAND_PRIMARY
    assert brand_primary_hex({}) == BRAND_PRIMARY
    assert brand_primary_hex(None) == BRAND_PRIMARY
    assert Brand({"name": "Design Saga", "branding": {"primary_color": "#002FA7"}}).primary == (118, 112, 94)


def test_a_chosen_colour_is_kept():
    assert brand_primary_hex({"primary_color": "#8B7A55"}) == "#8B7A55"
    assert Brand({"branding": {"primary_color": "#8B7A55"}}).primary == hex_to_rgb("#8B7A55")
