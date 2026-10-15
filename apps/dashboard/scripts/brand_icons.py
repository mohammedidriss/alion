"""Render the phone apps' icons and splash screens from the RingsideIQ mark (ADR-061).

    python scripts/brand_icons.py     (from apps/dashboard; needs rsvg-convert and Pillow)

Every existing image is replaced at its own size: the iOS app icon (full-bleed,
no transparency — the App Store refuses it), Android's launcher icons (square,
round, and the adaptive foreground with the ropes inside its safe zone), and
the splash screens (the mark centred on the dashboard's near-black).
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
BG = (10, 10, 15)  # #0a0a0f, the dashboard's background

GRADIENT = """<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#a78bfa"/><stop offset="100%" stop-color="#34d399"/>
</linearGradient></defs>"""
ROPES = """<rect x="12" y="13" width="5" height="38" rx="2.5" fill="#0a0a0f"/>
<rect x="47" y="13" width="5" height="38" rx="2.5" fill="#0a0a0f"/>
<g stroke="#0a0a0f" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" fill="none">
<path d="M17 21H47"/><path d="M17 32H25L28.5 24L33.5 40L37 32H47"/><path d="M17 43H47"/></g>"""


def _svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{GRADIENT}{body}</svg>'


def full_bleed(scale: float) -> str:
    """The gradient to every edge, the ropes scaled about the centre."""
    return _svg(
        f'<rect width="64" height="64" fill="url(#g)"/>'
        f'<g transform="translate(32 32) scale({scale}) translate(-32 -32)">{ROPES}</g>'
    )


MARK = _svg(f'<rect x="4" y="4" width="56" height="56" rx="14" fill="url(#g)"/>{ROPES}')


def render(svg: str, size: int) -> Image.Image:
    png = subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size)],
        input=svg.encode(),
        capture_output=True,
        check=True,
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def round_icon(size: int) -> Image.Image:
    img = render(full_bleed(0.72), size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def splash(w: int, h: int) -> Image.Image:
    out = Image.new("RGB", (w, h), BG)
    side = round(min(w, h) * 0.28)
    mark = render(MARK, side)
    out.paste(mark, ((w - side) // 2, (h - side) // 2), mark)
    return out


def main() -> None:
    ios = HERE / "ios/App/App/Assets.xcassets"
    render(full_bleed(0.8), 1024).convert("RGB").save(ios / "AppIcon.appiconset/AppIcon-512@2x.png")
    for p in sorted((ios / "Splash.imageset").glob("*.png")):
        w, h = Image.open(p).size
        splash(w, h).save(p)

    res = HERE / "android/app/src/main/res"
    for p in sorted(res.glob("mipmap-*/ic_launcher.png")):
        render(MARK, Image.open(p).size[0]).save(p)
    for p in sorted(res.glob("mipmap-*/ic_launcher_round.png")):
        round_icon(Image.open(p).size[0]).save(p)
    # Adaptive icons show the middle 72 of 108 dp, masked to the launcher's shape:
    # the gradient fills the layer, the ropes stay inside the safe zone.
    for p in sorted(res.glob("mipmap-*/ic_launcher_foreground.png")):
        render(full_bleed(0.55), Image.open(p).size[0]).save(p)
    for p in sorted(res.glob("drawable*/splash.png")):
        w, h = Image.open(p).size
        splash(w, h).save(p)


if __name__ == "__main__":
    main()
