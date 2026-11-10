"""Build the repository's social preview card from the braking screenshot.

Writes docs/social/social-preview.svg, the editable master (live text in Noto Sans, the screenshot crop embedded), and
renders it to docs/social/social-preview.png at 1280 × 640, the size GitHub recommends (PNG under 1 MB, solid
background). Run tools/screenshots.py first so that the crop shows the current window.

Colours are the app's palette (docs/illustrations.md): background #FAFAF7, ink #2B2A27, secondary text #5F5E5A,
frame #B4B2A9, the friction circle in teal #1D9E75 with its load point in coral #D85A30, the link in purple #534AB7.

Usage: QT_QPA_PLATFORM=offscreen python tools/social_preview.py
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "screenshots" / "00-braking.png"
OUT = ROOT / "docs" / "social"
WIDTH, HEIGHT = 1280, 640
CROP = QRect(12, 92, 1378, 512)  # the braking view and its six charts, in the 1400-pixel-wide screenshot
SLOT = (64, 182, 1152, 428)  # where the crop sits on the card: x, y, width, height (same aspect as the crop)
FONT = "Noto Sans, DejaVu Sans, sans-serif"
SUBTITLE = "A motorcycle simulator where braking and cornering share one grip budget."


def png_base64(image: QImage) -> str:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return base64.b64encode(bytes(data)).decode("ascii")


def svg(crop_png: str) -> str:
    x, y, w, h = SLOT
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{WIDTH}" height="{HEIGHT}"
     viewBox="0 0 {WIDTH} {HEIGHT}">
  <desc>Social preview card for the kammcircle repository. Master file: live text in Noto Sans (fallback DejaVu Sans);
  the screenshot is an embedded crop of docs/screenshots/00-braking.png. Regenerate with tools/social_preview.py.</desc>
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#FAFAF7"/>
  <g id="friction-circle">
    <circle cx="94" cy="84" r="27" fill="none" stroke="#1D9E75" stroke-width="5"/>
    <line x1="64" y1="84" x2="124" y2="84" stroke="#B4B2A9" stroke-width="1.5"/>
    <line x1="94" y1="54" x2="94" y2="114" stroke="#B4B2A9" stroke-width="1.5"/>
    <circle cx="108" cy="72" r="6" fill="#D85A30"/>
  </g>
  <text x="138" y="106" font-family="{FONT}" font-size="62" font-weight="bold" fill="#2B2A27">kammcircle</text>
  <text x="{WIDTH - 64}" y="104" font-family="{FONT}" font-size="21" fill="#534AB7"
        text-anchor="end">github.com/achrafsoltani/kammcircle</text>
  <text x="64" y="158" font-family="{FONT}" font-size="27" fill="#5F5E5A">{SUBTITLE}</text>
  <rect x="{x - 2}" y="{y - 2}" width="{w + 4}" height="{h + 4}" fill="#FFFFFF" stroke="#B4B2A9" stroke-width="2"/>
  <image x="{x}" y="{y}" width="{w}" height="{h}" xlink:href="data:image/png;base64,{crop_png}"/>
</svg>
"""


def main() -> int:
    QGuiApplication(sys.argv[:1])
    shot = QImage(str(SOURCE))
    if shot.isNull() or shot.width() < CROP.right() or shot.height() < CROP.bottom():
        print(f"{SOURCE} is missing or smaller than the crop; run tools/screenshots.py first", file=sys.stderr)
        return 1
    crop = shot.copy(CROP)
    OUT.mkdir(parents=True, exist_ok=True)
    text = svg(png_base64(crop))
    (OUT / "social-preview.svg").write_text(text, encoding="utf-8")
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
    image.fill(QColor("#FAFAF7"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    png = OUT / "social-preview.png"
    image.save(str(png), "PNG")
    size = png.stat().st_size
    print(f"wrote {png.relative_to(ROOT)} ({WIDTH} × {HEIGHT}, {size / 1024:.0f} KB) and social-preview.svg")
    return 0 if size < 1_000_000 else 2


if __name__ == "__main__":
    sys.exit(main())
