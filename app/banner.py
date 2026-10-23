"""Optional "Aggressor VS Defender" banner image (PNG), uploaded as a Discord attachment."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .config import Settings
from .embeds import logo_url
from .models import Party, War

log = logging.getLogger(__name__)

W, H, LOGO = 640, 220, 128
BG, FG, ACCENT = (24, 26, 32), (235, 235, 235), (192, 57, 43)
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]


def _font(size: int):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                       # Pillow < 10.1
        return ImageFont.load_default()


def _download_logo(p: Party, s: Settings, ua: str) -> Image.Image | None:
    for url in filter(None, [logo_url(p, s, LOGO), p.logo_url_small]):
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=10)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA").resize((LOGO, LOGO))
        except Exception as e:
            log.debug("logo download failed %s: %s", url, e)
    return None


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def render_banner(w: War, s: Settings, ua: str) -> bytes | None:
    a_img, d_img = _download_logo(w.aggressor, s, ua), _download_logo(w.defender, s, ua)
    if not a_img or not d_img:
        return None
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 4], fill=ACCENT)
    y = 24
    ax, dx = 56, W - 56 - LOGO
    img.paste(a_img, (ax, y), a_img)
    img.paste(d_img, (dx, y), d_img)
    vs_font, name_font = _font(48), _font(16)
    draw.text((W // 2, y + LOGO // 2), "VS", font=vs_font, fill=ACCENT, anchor="mm")
    for x, p in ((ax, w.aggressor), (dx, w.defender)):
        name = _fit(draw, p.name, name_font, 220)
        draw.text((x + LOGO // 2, y + LOGO + 22), name, font=name_font, fill=FG, anchor="mm")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
