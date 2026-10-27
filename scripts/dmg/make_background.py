"""Draw the DMG window background: TrackMate on the left, an arrow, Applications on the right.
The instructions sit at the top: Finder's path and status bars, when the user has them on,
cover the bottom of the window.

Writes background.png (640x400) and background@2x.png next to this script; dmgbuild combines
them into one HiDPI image. Icon centres must match icon_locations in settings.py.
Usage: uvx --with pillow python scripts/dmg/make_background.py
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE.parents[1] / "app" / "assets" / "fonts"
W, H = 640, 400
APP, APPS = (170, 200), (470, 200)       # icon centres (settings.py icon_locations)
TOP, BOTTOM = (250, 250, 252), (236, 236, 241)
ACCENT = (91, 91, 214)                    # the README buttons' colour (#5B5BD6)
TEXT, MUTED = (40, 40, 48), (110, 110, 122)


def draw(scale: int) -> Image.Image:
    s = scale * 4  # draw large, then reduce: smooth edges
    img = Image.new("RGB", (W * s, H * s))
    px = ImageDraw.Draw(img)
    for y in range(H * s):  # soft vertical gradient
        t = y / (H * s - 1)
        px.line([(0, y), (W * s, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    # arrow between the icons
    y = APP[1] * s
    x0, x1 = (APP[0] + 92) * s, (APPS[0] - 92) * s
    head = 16 * s
    px.rounded_rectangle([x0, y - 3 * s, x1 - head + 2 * s, y + 3 * s], radius=3 * s, fill=ACCENT)
    px.polygon([(x1, y), (x1 - head, y - 13 * s), (x1 - head, y + 13 * s)], fill=ACCENT)
    # instructions
    title = ImageFont.truetype(str(FONTS / "Geist-SemiBold.ttf"), 20 * s)
    body = ImageFont.truetype(str(FONTS / "Geist-Regular.ttf"), 14 * s)
    for text, font, colour, top in (("Drag TrackMate to Applications", title, TEXT, 34),
                                    ("Then open it from Launchpad or the Applications folder.", body, MUTED, 64)):
        w = px.textlength(text, font=font)
        px.text(((W * s - w) / 2, top * s), text, font=font, fill=colour)
    return img.resize((W * scale, H * scale), Image.LANCZOS)


if __name__ == "__main__":
    draw(1).save(HERE / "background.png", dpi=(72, 72))
    draw(2).save(HERE / "background@2x.png", dpi=(144, 144))
    print("wrote", HERE / "background.png", HERE / "background@2x.png")
