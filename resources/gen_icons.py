"""Generate simple flat-color function icons for the app (toolbar/tabs) and
a .desktop launcher icon. Run once at build time; output is committed so the
app doesn't need Pillow at runtime.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "icons"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 128
BG = (255, 255, 255, 0)


def canvas():
    img = Image.new("RGBA", (SIZE, SIZE), BG)
    return img, ImageDraw.Draw(img)


def rounded_bg(draw, color):
    draw.rounded_rectangle((4, 4, SIZE - 4, SIZE - 4), radius=24, fill=color)


def save(img, name):
    img.save(OUT / f"{name}.png")


def icon_app():
    img, d = canvas()
    rounded_bg(d, (35, 95, 135, 255))
    d.rectangle((30, 34, 98, 44), fill="white")
    d.rectangle((30, 54, 98, 64), fill="white")
    d.rectangle((30, 74, 78, 84), fill="white")
    d.ellipse((80, 74, 100, 94), outline="white", width=4)
    save(img, "app")


def icon_dashboard():
    img, d = canvas()
    rounded_bg(d, (52, 120, 165, 255))
    bars = [(30, 70, 46, 96), (54, 50, 70, 96), (78, 30, 94, 96)]
    for box in bars:
        d.rectangle(box, fill="white")
    save(img, "dashboard")


def icon_clients():
    img, d = canvas()
    rounded_bg(d, (60, 140, 120, 255))
    d.ellipse((44, 24, 84, 64), fill="white")
    d.pieslice((24, 64, 104, 130), start=180, end=360, fill="white")
    save(img, "clients")


def icon_documents():
    img, d = canvas()
    rounded_bg(d, (150, 110, 60, 255))
    d.rectangle((36, 24, 92, 104), fill="white")
    for y in (40, 54, 68, 82):
        d.rectangle((44, y, 84, y + 6), fill=(150, 110, 60, 255))
    save(img, "documents")


def icon_ledger():
    img, d = canvas()
    rounded_bg(d, (120, 70, 150, 255))
    d.rectangle((28, 30, 100, 98), outline="white", width=5)
    for y in (44, 58, 72, 86):
        d.line((36, y, 92, y), fill="white", width=4)
    d.line((64, 30, 64, 98), fill="white", width=3)
    save(img, "ledger")


def icon_import():
    img, d = canvas()
    rounded_bg(d, (170, 90, 60, 255))
    d.rectangle((44, 24, 84, 70), fill="white")
    d.polygon([(34, 70), (94, 70), (64, 100)], fill="white")
    d.rectangle((30, 104, 98, 112), fill="white")
    save(img, "import")


def icon_facturx():
    img, d = canvas()
    rounded_bg(d, (40, 130, 90, 255))
    d.rectangle((30, 24, 78, 104), fill="white")
    d.ellipse((66, 60, 106, 100), fill=(40, 130, 90, 255), outline="white", width=4)
    d.line((78, 80, 88, 90), fill="white", width=4)
    d.line((88, 90, 98, 72), fill="white", width=4)
    save(img, "facturx")


def icon_declarations():
    img, d = canvas()
    rounded_bg(d, (180, 130, 40, 255))
    d.polygon([(64, 24), (100, 44), (100, 84), (64, 104), (28, 84), (28, 44)], fill="white")
    d.line((50, 66, 60, 78), fill=(180, 130, 40, 255), width=6)
    d.line((60, 78, 82, 50), fill=(180, 130, 40, 255), width=6)
    save(img, "declarations")


def icon_settings():
    img, d = canvas()
    rounded_bg(d, (90, 90, 100, 255))
    d.ellipse((44, 44, 84, 84), fill="white")
    d.ellipse((56, 56, 72, 72), fill=(90, 90, 100, 255))
    for angle_box in [
        (60, 20, 68, 36), (60, 92, 68, 108),
        (20, 60, 36, 68), (92, 60, 108, 68),
    ]:
        d.rectangle(angle_box, fill="white")
    save(img, "settings")


if __name__ == "__main__":
    icon_app()
    icon_dashboard()
    icon_clients()
    icon_documents()
    icon_ledger()
    icon_import()
    icon_facturx()
    icon_declarations()
    icon_settings()
    print("Icons written to", OUT)
