from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 1024
OUTPUT_DIR = Path(__file__).resolve().parent / "electron"


def mix(start, end, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def text_gradient(image, text, font, position, start, end):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).text(position, text, font=font, fill=255)
    bounds = mask.getbbox()
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    gradient = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(gradient)
    for x in range(width):
        draw.line((x, 0, x, height), fill=(*mix(start, end, x / max(width - 1, 1)), 255))
    gradient.putalpha(mask.crop(bounds))
    image.alpha_composite(gradient, (left, top))


def make_icon():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    background = Image.new("RGBA", image.size)
    background_draw = ImageDraw.Draw(background)
    top = (14, 31, 61)
    bottom = (39, 25, 72)
    for y in range(SIZE):
        background_draw.line((0, y, SIZE, y), fill=(*mix(top, bottom, y / (SIZE - 1)), 255))

    glow = Image.new("RGBA", image.size)
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-170, -120, 530, 580), fill=(48, 174, 244, 115))
    glow_draw.ellipse((500, 470, 1190, 1160), fill=(152, 84, 231, 125))
    background.alpha_composite(glow.filter(ImageFilter.GaussianBlur(145)))

    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((18, 18, SIZE - 18, SIZE - 18), radius=224, fill=255)
    background.putalpha(mask)
    image.alpha_composite(background)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((106, 100, 918, 924), radius=144, fill=(12, 22, 47, 92), outline=(157, 193, 255, 88), width=5)
    draw.polygon([(716, 102), (916, 102), (916, 301)], fill=(147, 119, 239, 126))
    draw.line([(716, 102), (716, 301), (916, 301)], fill=(175, 211, 255, 112), width=5)

    font_paths = [
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    font_path = next((path for path in font_paths if path.exists()), None)
    font = ImageFont.truetype(str(font_path), 326) if font_path else ImageFont.load_default()
    metrics = ImageDraw.Draw(image)
    gap = 8
    d_width = metrics.textlength("D", font=font)
    rest_width = metrics.textlength("2M", font=font)
    x = (SIZE - d_width - gap - rest_width) / 2
    bbox = metrics.textbbox((0, 0), "D2M", font=font)
    y = int(478 - (bbox[3] - bbox[1]) / 2 - bbox[1])

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text((x + 3, y + 16), "D2M", font=font, fill=(4, 8, 24, 190), stroke_width=8, stroke_fill=(4, 8, 24, 190))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(15)))

    text_gradient(image, "D", font, (x, y), (89, 205, 255), (151, 240, 255))
    text_gradient(image, "2M", font, (x + d_width + gap, y), (159, 146, 255), (222, 171, 255))

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((330, 742, 694, 764), radius=11, fill=(105, 207, 255, 220))
    draw.rounded_rectangle((330, 790, 608, 812), radius=11, fill=(169, 160, 255, 204))
    draw.rounded_rectangle((330, 838, 518, 860), radius=11, fill=(203, 174, 255, 180))
    draw.rounded_rectangle((18, 18, SIZE - 18, SIZE - 18), radius=224, outline=(176, 209, 255, 108), width=5)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUTPUT_DIR / "app-icon.png"
    ico_path = OUTPUT_DIR / "app-icon.ico"
    icns_path = OUTPUT_DIR / "app-icon.icns"
    image.save(png_path, "PNG", optimize=True)
    image.save(ico_path, "ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.save(icns_path, "ICNS")


if __name__ == "__main__":
    make_icon()
