#!/usr/bin/env python

from PIL import Image, ImageOps


def process_app_assets(
    source_path="assets/src_icon.png",
    icon_out="assets/custom_icon.png",
    bg_color=(127, 127, 127) # White background (R, G, B)
):
    # Load source artwork and ensure RGBA mode
    img = Image.open(source_path).convert("RGBA")
    print(f"img = {img.width}x{img.height}")
    canvas_size = (1920, 1920)

    # Scale source artwork proportionally so it fits within 1024x1024 without distortion
    contained_art = ImageOps.contain(img, (1800, 1800), method=Image.Resampling.LANCZOS)
    print(f"cart = {contained_art.width}x{contained_art.height}")

    # Calculate offset coordinates to center the contained artwork on the 1024x1024 canvas
    offset = (
        (canvas_size[0] - contained_art.width) // 2,
        (canvas_size[1] - contained_art.height) // 2
    )
    print(offset)

    # 2. Generate Centered Opaque App Icon for TestFlight (1024x1024 RGB)
    icon_background = Image.new("RGB", canvas_size, bg_color)
    icon_background.paste(contained_art, offset, mask=contained_art.split()[3])
    icon_background.save(icon_out, format="PNG")
    print(f"Saved opaque centered 1920x1920 app icon to {icon_out}")

if __name__ == "__main__":
    process_app_assets()
