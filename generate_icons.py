#!/usr/bin/env python3

import sys
from pathlib import Path

from PIL import Image, ImageColor, ImageOps

# --- CONFIGURATION ---
SRC_ICON = Path("assets/src_icon.png")
OUTPUT_DIR = Path("assets/icons")

# Hex background color for iOS & opaque canvases
# Match this to `splash_background_color` in pyproject.toml
SPLASH_BACKGROUND_COLOR = "#7F7F7F"

# iOS Squircle Safe Area Padding (0.20 = 20% margin around inner symbol)
IOS_PADDING_PERCENT = 0.20

# --- SIZES & REQUIREMENTS ---
IOS_SIZES = [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 640, 1024, 1280, 1920]
DESKTOP_SIZES = [16, 32, 48, 64, 72, 96, 128, 192, 256, 512, 1024]

# Briefcase-specific Android variants: (variant_name, size)
ANDROID_BRIEFCASE_SPECS = [
    # Legacy Square & Round variants
    ("square", 48), ("square", 72), ("square", 96), ("square", 144), ("square", 192),
    ("round", 48),  ("round", 72),  ("round", 96),  ("round", 144),  ("round", 192),
    # Adaptive variants (Foreground layer dimensions)
    ("adaptive", 108), ("adaptive", 162), ("adaptive", 216), ("adaptive", 324), ("adaptive", 432)
]


def render_icon_canvas(
    img: Image.Image,
    target_size: int,
    bg_hex: str | None = None,
    padding_pct: float = 0.0,
    opaque: bool = False
) -> Image.Image:
    """
    Resizes `img` maintaining aspect ratio using ImageOps.contain, centers it onto 
    a square canvas of `target_size` x `target_size`, applying optional background 
    fill and padding.
    """
    # 1. Determine inner bounding box accounting for padding
    inner_size = int(target_size * (1.0 - (padding_pct * 2)))
    inner_size = max(inner_size, 1)

    # 2. Resize maintaining aspect ratio using ImageOps.contain
    contained_img = ImageOps.contain(img, (inner_size, inner_size), method=Image.Resampling.LANCZOS)

    # 3. Create canvas (transparent or solid color)
    if bg_hex:
        bg_color = ImageColor.getcolor(bg_hex, "RGBA")
    else:
        bg_color = (0, 0, 0, 0) # Fully transparent canvas

    canvas = Image.new("RGBA", (target_size, target_size), bg_color)

    # 4. Paste contained image centered on canvas
    offset_x = (target_size - contained_img.width) // 2
    offset_y = (target_size - contained_img.height) // 2
    canvas.alpha_composite(contained_img, (offset_x, offset_y))

    # 5. Drop alpha channel for strict opacity compliance (e.g. iOS)
    if opaque:
        return canvas.convert("RGB")

    return canvas


def generate_all_icons():
    if not SRC_ICON.exists():
        print(f"Error: Source image '{SRC_ICON}' not found.")
        print("Please place a high-resolution PNG at assets/src_icon.png")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with Image.open(SRC_ICON) as raw_img:
        img = raw_img.convert("RGBA")
        width, height = img.size
        print(f"Loaded source image: {SRC_ICON} ({width}x{height}px)")

        # --- 1. iOS ICONS (Opaque RGB + Padded + Aspect Preserved) ---
        print(f"\n--- 1. Generating iOS Icons ({int(IOS_PADDING_PERCENT*100)}% Padding, Opaque) ---")
        ios_dir = OUTPUT_DIR / "ios"
        ios_dir.mkdir(parents=True, exist_ok=True)

        for size in IOS_SIZES:
            ios_icon = render_icon_canvas(
                img,
                target_size=size,
                bg_hex=SPLASH_BACKGROUND_COLOR,
                padding_pct=IOS_PADDING_PERCENT,
                opaque=True
            )
            out_path = ios_dir / f"icon-{size}.png"
            ios_icon.save(out_path, format="PNG")
            print(f"  Saved: {out_path} ({size}x{size}px)")

        # --- 2. DESKTOP PNGs (Transparent + Centered Aspect Ratio) ---
        print("\n--- 2. Generating Desktop PNGs ---")
        png_dir = OUTPUT_DIR / "png"
        png_dir.mkdir(parents=True, exist_ok=True)

        for size in DESKTOP_SIZES:
            desktop_icon = render_icon_canvas(img, target_size=size)
            out_path = png_dir / f"icon-{size}.png"
            desktop_icon.save(out_path, format="PNG")
            print(f"  Saved: {out_path}")

        # --- 3. ANDROID ICONS (Briefcase Flat Filename Pattern) ---
        print("\n--- 3. Generating Android Briefcase Icons ---")
        android_dir = OUTPUT_DIR / "android"
        android_dir.mkdir(parents=True, exist_ok=True)
        for variant, size in ANDROID_BRIEFCASE_SPECS:
            # Adaptive layers need safe-zone margin (18%)
            padding = 0.18 if variant == "adaptive" else 0.0

            android_icon = render_icon_canvas(
                img,
                target_size=size,
                padding_pct=padding
            )
            out_path = android_dir / f"icon-{variant}-{size}.png"
            android_icon.save(out_path, format="PNG")
            print(f"  Saved: {out_path}")

        # --- 4. WINDOWS ICO ---
        print("\n--- 4. Generating Windows Multi-Resolution ICO ---")
        ico_canvas = render_icon_canvas(img, target_size=256)
        ico_path = OUTPUT_DIR / "icon.ico"
        ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        ico_canvas.save(ico_path, format="ICO", sizes=ico_sizes)
        print(f"  Saved: {ico_path}")

        # --- 5. macOS ICNS ---
        print("\n--- 5. Generating macOS ICNS Container ---")
        icns_canvas = render_icon_canvas(img, target_size=1024)
        icns_path = OUTPUT_DIR / "icon.icns"
        icns_canvas.save(icns_path, format="ICNS")
        print(f"  Saved: {icns_path}")

    print("\nIcon generation complete!")


if __name__ == "__main__":
    generate_all_icons()
