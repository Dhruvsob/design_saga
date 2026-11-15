"""Stamp superseded drawing files when they are opened.

The stored original is never modified: the stamp is added to the copy that is
served. PDFs get a large translucent diagonal "SUPERSEDED" and a red banner
naming the current revision on every page (any page size); PNG/JPEG/WEBP
images get the same diagonal stamp. Anything else is served unchanged.

Callers treat a stamping error as "serve the original": the app already shows
a SUPERSEDED banner next to every preview, so a damaged PDF never blocks access.
"""
import io
import math
from typing import Optional

STAMP = "SUPERSEDED"


def banner(current_rev: Optional[str]) -> str:
    return (f"SUPERSEDED - revision {current_rev} is current. Do not use this sheet for work."
            if current_rev else "SUPERSEDED - do not use this sheet for work.")


def _overlay_pdf(width: float, height: float, current_rev: Optional[str]) -> bytes:
    from fpdf import FPDF
    pdf = FPDF(unit="pt", format=(width, height))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.add_page()
    size = max(28.0, min(width, height) / 7)
    pdf.set_font("Helvetica", "B", size)
    pdf.set_text_color(178, 43, 34)
    text_w = pdf.get_string_width(STAMP)
    angle = math.degrees(math.atan2(height, width))
    with pdf.local_context(fill_opacity=0.28, stroke_opacity=0.28):
        with pdf.rotation(angle, x=width / 2, y=height / 2):
            pdf.text(width / 2 - text_w / 2, height / 2 + size / 3, STAMP)
    bar = max(14.0, min(width, height) / 40)
    pdf.set_font("Helvetica", "B", bar * 0.62)
    pdf.set_fill_color(178, 43, 34)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(0, 0)
    pdf.cell(width, bar, banner(current_rev), align="C", fill=True)
    return bytes(pdf.output())


def stamp_pdf(data: bytes, current_rev: Optional[str]) -> bytes:
    from pypdf import PdfReader, PdfWriter, Transformation
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("encrypted PDF")
    writer = PdfWriter()
    overlays = {}
    for page in reader.pages:
        box = page.mediabox
        w, h = float(box.width), float(box.height)
        key = (round(w, 1), round(h, 1))
        if key not in overlays:
            overlays[key] = PdfReader(io.BytesIO(_overlay_pdf(w, h, current_rev))).pages[0]
        page.merge_transformed_page(overlays[key], Transformation().translate(float(box.left), float(box.bottom)))
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def stamp_image(data: bytes, current_rev: Optional[str]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(io.BytesIO(data)) as src:
        fmt = src.format or "PNG"
        base = src.convert("RGBA")
    w, h = base.size
    size = max(18, int(min(w, h) / 7))
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:        # very old Pillow: fixed-size bitmap font
        font = ImageFont.load_default()
    left, top, right, bottom = ImageDraw.Draw(base).textbbox((0, 0), STAMP, font=font)
    label = Image.new("RGBA", (right - left + 20, bottom - top + 20), (0, 0, 0, 0))
    ImageDraw.Draw(label).text((10 - left, 10 - top), STAMP, font=font, fill=(178, 43, 34, 90))
    label = label.rotate(math.degrees(math.atan2(h, w)), expand=True)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(label, ((w - label.width) // 2, (h - label.height) // 2), label)
    bar = max(16, h // 30)
    draw = ImageDraw.Draw(layer)
    draw.rectangle([0, 0, w, bar], fill=(178, 43, 34, 230))
    try:
        small = ImageFont.load_default(size=max(10, int(bar * 0.6)))
    except TypeError:
        small = ImageFont.load_default()
    draw.text((8, max(1, bar // 6)), banner(current_rev), font=small, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(base, layer)
    buf = io.BytesIO()
    if fmt.upper() in ("JPEG", "JPG"):
        out.convert("RGB").save(buf, "JPEG", quality=90)
    else:
        out.save(buf, fmt.upper() if fmt.upper() in ("PNG", "WEBP") else "PNG")
    return buf.getvalue()


def stamp(data: bytes, media_type: str, current_rev: Optional[str]) -> bytes:
    """Stamp a superseded file; returns the input unchanged for other types."""
    media = (media_type or "").split(";")[0].strip().lower()
    if media == "application/pdf":
        return stamp_pdf(data, current_rev)
    if media in ("image/png", "image/jpeg", "image/webp"):
        return stamp_image(data, current_rev)
    return data


async def serve_drawing_file(file_doc: dict, current_rev: Optional[str], superseded: bool):
    """FileResponse for a current sheet; a stamped copy for a superseded one."""
    import asyncio
    import logging

    from fastapi import HTTPException
    from fastapi.responses import FileResponse, Response

    from core.downloads import content_disposition
    from services.local_files import resolve_storage_key

    if not file_doc or not file_doc.get("storage_key"):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        path = resolve_storage_key(file_doc["storage_key"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is unavailable")
    media = file_doc.get("content_type") or "application/octet-stream"
    name = file_doc.get("original_name") or file_doc.get("name") or "drawing"
    disposition = "inline" if media == "application/pdf" or media.startswith("image/") else "attachment"
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if not superseded:
        return FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition,
                            headers=headers)
    data = await asyncio.to_thread(path.read_bytes)
    try:
        data = await asyncio.to_thread(stamp, data, media, current_rev)
        headers["X-Superseded-Stamp"] = "applied"
    except Exception as exc:  # noqa: BLE001 - serve the original; the UI still shows the banner
        logging.getLogger("stamp").warning("superseded stamp failed: %s", type(exc).__name__)
        headers["X-Superseded-Stamp"] = "failed"
    stem, dot, ext = name.rpartition(".")
    stamped_name = f"{stem}-SUPERSEDED.{ext}" if dot else f"{name}-SUPERSEDED"
    headers["Content-Disposition"] = content_disposition(disposition, stamped_name, "drawing")
    return Response(content=data, media_type=media, headers=headers)
