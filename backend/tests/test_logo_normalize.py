"""Uploaded logos are trimmed of empty borders and size-capped (DS-086)."""
import io

import pytest
from PIL import Image, ImageDraw

from services import storage


def _encode(img, fmt):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def _artwork_box(png_bytes):
    with Image.open(io.BytesIO(png_bytes)) as img:
        return img.size, img.convert("RGBA").getbbox()


def test_white_canvas_jpeg_is_trimmed_to_the_artwork():
    canvas = Image.new("RGB", (3000, 3000), "white")
    ImageDraw.Draw(canvas).rectangle((1200, 1000, 1800, 2000), fill="black")
    out, mime = storage.normalize_logo(_encode(canvas, "JPEG"))
    assert mime == "image/png"
    with Image.open(io.BytesIO(out)) as img:
        w, h = img.size
    # 600x1000 artwork + 4% margin each side, well under the 1200px cap
    assert 600 < w < 700 and 1000 < h < 1100


def test_transparent_canvas_is_trimmed_by_alpha():
    canvas = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse((800, 300, 1200, 700), fill=(20, 20, 20, 255))
    out, _ = storage.normalize_logo(_encode(canvas, "PNG"))
    (w, h), _bbox = _artwork_box(out)
    assert w < 500 and h < 500


def test_large_logo_is_capped_and_aspect_preserved():
    art = Image.new("RGB", (4000, 2000), (139, 127, 106))
    ImageDraw.Draw(art).rectangle((0, 0, 3999, 999), fill="black")
    out, _ = storage.normalize_logo(_encode(art, "PNG"))
    with Image.open(io.BytesIO(out)) as img:
        assert max(img.size) == storage.LOGO_MAX_SIDE
        assert abs(img.width / img.height - 2.0) < 0.01


def test_busy_edges_are_left_untouched():
    art = Image.new("RGB", (300, 200), "red")
    ImageDraw.Draw(art).rectangle((0, 0, 149, 199), fill="blue")
    out, _ = storage.normalize_logo(_encode(art, "PNG"))
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (300, 200)


def test_data_url_upload_stores_the_normalised_png(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    canvas = Image.new("RGB", (1500, 1500), "white")
    ImageDraw.Draw(canvas).rectangle((600, 600, 900, 900), fill="black")
    import base64
    data_url = "data:image/jpeg;base64," + base64.b64encode(_encode(canvas, "JPEG")).decode()
    stored = {}
    monkeypatch.setattr(storage, "put_object",
                        lambda path, raw, mime: stored.update(path=path, raw=raw, mime=mime) or {"path": path})
    info = storage.upload_data_url(data_url, folder="org-logos", owner_id="org_test",
                                   allowed_mimes=storage.ALLOWED_LOGO_MIME)
    assert info["mime"] == "image/png" and info["path"].endswith(".png")
    assert storage.LOGO_PATH_RE.match(info["path"])
    with Image.open(io.BytesIO(stored["raw"])) as img:
        assert max(img.size) < 400


def test_unreadable_image_is_rejected():
    with pytest.raises(ValueError):
        storage.upload_data_url("data:image/png;base64," + "iVBORw0KGgo" + "A" * 40,
                                folder="org-logos", owner_id="org_test",
                                allowed_mimes=storage.ALLOWED_LOGO_MIME)
