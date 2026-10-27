"""Draws the TrackMate app icon and writes every size macOS needs into
macos/Runner/Assets.xcassets/AppIcon.appiconset.

Motif: a short list of track lanes, each with a category-coloured dot (the app's job: name,
colour and group tracks), and a check badge in the app's accent colour (done, ready to mix).
Colours come from lib/ui/theme.dart and the Pro Tools palette.

Run: uv run --no-project --with pillow python macos/icon/make_icon.py
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
S = 2048  # drawn at 2x and scaled down for smooth edges

ACCENT = (140, 140, 247)
LANE = (232, 232, 238)
# Category colours from the Pro Tools palette used in the app (drums, bass, keys, lead vocals).
DOTS = [(188, 0, 13), (136, 0, 252), (46, 198, 15), (33, 132, 252)]


def u(v: float) -> int:
    """Units of the 1024 icon grid to pixels."""
    return round(v * S / 1024)


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Body: the macOS icon grid (824 x 824 at 100, 100), with a soft shadow.
    body = (u(100), u(100), u(924), u(924))
    radius = u(186)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((body[0], body[1] + u(12), body[2], body[3] + u(12)),
                                             radius, fill=(0, 0, 0, 110))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(u(18))))

    # Vertical gradient from panel grey to window black.
    grad = Image.new("RGBA", (S, S))
    top, bottom = (44, 44, 54), (19, 19, 22)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = min(max((y - body[1]) / (body[3] - body[1]), 0), 1)
        gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(body, radius, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(body, radius, outline=(255, 255, 255, 28), width=u(3))

    # Track lanes: dot + audio clip of different lengths (the last two shortened by the badge),
    # each clip with a small waveform so the list reads as audio tracks, not a to-do list.
    lanes = [(330, 720), (450, 650), (570, 600), (690, 520)]
    for k, ((y, end), dot) in enumerate(zip(lanes, DOTS)):
        d.ellipse((u(232 - 30), u(y - 30), u(232 + 30), u(y + 30)), fill=dot + (255,))
        d.rounded_rectangle((u(294), u(y - 30), u(end), u(y + 30)), u(30), fill=LANE + (235,))
        for i, x in enumerate(range(326, end - 26, 22)):
            h = 6 + 16 * abs(((i * 7 + k * 5) % 11) - 5) / 5  # deterministic "waveform"
            d.rounded_rectangle((u(x - 4), u(y - h), u(x + 4), u(y + h)), u(4), fill=(70, 70, 86, 255))

    # Check badge with a ring in the body colour so it separates from the lanes.
    cx, cy, r = 700, 712, 132
    d.ellipse((u(cx - r - 18), u(cy - r - 18), u(cx + r + 18), u(cy + r + 18)), fill=(24, 24, 28, 255))
    d.ellipse((u(cx - r), u(cy - r), u(cx + r), u(cy + r)), fill=ACCENT + (255,))
    d.line([(u(cx - 62), u(cy + 4)), (u(cx - 16), u(cy + 50)), (u(cx + 66), u(cy - 44))],
           fill=(16, 16, 20, 255), width=u(34), joint="curve")
    for x, y in [(cx - 62, cy + 4), (cx - 16, cy + 50), (cx + 66, cy - 44)]:  # round line caps
        d.ellipse((u(x - 17), u(y - 17), u(x + 17), u(y + 17)), fill=(16, 16, 20, 255))
    return img.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    icon = draw()
    for size in (16, 32, 64, 128, 256, 512, 1024):
        icon.resize((size, size), Image.LANCZOS).save(OUT / f"app_icon_{size}.png")
    icon.save(HERE / "trackmate_icon_1024.png")
    win = HERE.parents[1] / "windows" / "runner" / "resources" / "app_icon.ico"
    if win.parent.exists():
        icon.save(win, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
