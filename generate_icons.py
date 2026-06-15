"""Run once to generate PWA icons: python generate_icons.py"""
from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs("static", exist_ok=True)

def make_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), "#1d4ed8")  # blue-700
    draw = ImageDraw.Draw(img)

    text = "Rp"
    font_size = size // 3

    font = None
    for name in ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) // 2 - bbox[0]
    y = (size - h) // 2 - bbox[1]
    draw.text((x, y), text, fill="white", font=font)
    return img

for sz in [192, 512]:
    make_icon(sz).save(f"static/icon-{sz}.png")
    print(f"  static/icon-{sz}.png")

print("Done.")
