"""
Generate favicon.ico (16/32/48) and apple-touch-icon.png (180) from the same
design used in public/favicon.svg:

  - indigo-700 (#4338ca) rounded square
  - amber-400 (#fbbf24) plus sign with thick rounded strokes

Run after editing the design:
    python scripts/make_favicon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

# Design parameters (relative to a 64×64 viewport, matches favicon.svg)
BG_COLOR     = (67, 56, 202, 255)    # #4338ca indigo-700
FG_COLOR     = (251, 191, 36, 255)   # #fbbf24 amber-400
CORNER_RATIO = 12 / 64               # rx in svg
STROKE_RATIO = 10 / 64               # plus stroke width
INNER_RATIO  = (50 - 14) / 64        # plus arm length


def render(size: int) -> Image.Image:
    """Render the favicon at the given pixel size, anti-aliased via super-sampling."""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = int(s * CORNER_RATIO)
    # rounded rect bg
    draw.rounded_rectangle((0, 0, s, s), radius=radius, fill=BG_COLOR)

    stroke = max(2, int(s * STROKE_RATIO))
    arm = int(s * INNER_RATIO / 2)
    cx, cy = s // 2, s // 2

    # plus sign: two thick rounded lines crossing at center
    draw.line((cx - arm, cy, cx + arm, cy), fill=FG_COLOR, width=stroke)
    draw.line((cx, cy - arm, cx, cy + arm), fill=FG_COLOR, width=stroke)

    # round the line caps explicitly by stamping circles at the line ends
    cap_r = stroke // 2
    for x, y in [(cx - arm, cy), (cx + arm, cy), (cx, cy - arm), (cx, cy + arm)]:
        draw.ellipse((x - cap_r, y - cap_r, x + cap_r, y + cap_r), fill=FG_COLOR)

    # Downscale to target with high-quality filter
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # Multi-resolution favicon.ico (16, 32, 48 — the sizes browsers actually use)
    ico_sizes = [16, 32, 48]
    ico_images = [render(s) for s in ico_sizes]
    ico_path = PUBLIC / "favicon.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:],
    )
    print(f"Wrote {ico_path}  sizes={ico_sizes}")

    # 32×32 PNG (general purpose <link rel='icon'>)
    png_path = PUBLIC / "favicon-32.png"
    render(32).save(png_path, format="PNG", optimize=True)
    print(f"Wrote {png_path}")

    # 180×180 apple-touch-icon
    apple_path = PUBLIC / "apple-touch-icon.png"
    render(180).save(apple_path, format="PNG", optimize=True)
    print(f"Wrote {apple_path}")


if __name__ == "__main__":
    main()
