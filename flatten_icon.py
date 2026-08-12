#!/usr/bin/env python

from PIL import Image, ImageOps

def process_app_assets(
    source_path="assets/src_icon.png",
    icon_out="assets/custom_icon.png",
    bg_color=(127, 127, 127) # White background (R, G, B)
):
    # Load source artwork and ensure RGBA mode
    img = Image.open(source_path).convert("RGBA")
    canvas_size = (1920, 1920)

    # Scale source artwork proportionally so it fits within 1024x1024 without distortion
    contained_art = ImageOps.contain(img, (1800, 1800), method=Image.Resampling.LANCZOS)
    
    # Calculate offset coordinates to center the contained artwork on the 1024x1024 canvas
    offset = (
        (canvas_size[0] - contained_art.width) // 2,
        (canvas_size[1] - contained_art.height) // 2
    )

    # 2. Generate Centered Opaque App Icon for TestFlight (1024x1024 RGB)
    icon_background = Image.new("RGB", canvas_size, bg_color)
    icon_background.paste(contained_art, offset, mask=contained_art.split()[3])
    icon_background.save(icon_out, format="PNG")
    print(f"✓ Saved opaque centered19204x9204 app icon to {icon_out}")

if __name__ == "__main__":
    process_app_assets()



from PIL import Image

def process_app_assets(
    source_path="assets/src_icon.png",
    icon_out="assets/custom_icon.png",
    bg_color=(127, 127, 127) # White background (R, G, B)
):
    # Load source artwork and convert to RGBA
    img = Image.open(source_path).convert("RGBA")
    
    # 2. Generate Opaque App Icon for TestFlight (1024x1024 RGB)
    # Create a solid canvas with no alpha channel
    background = Image.new("RGB", (1920, 1920), bg_color)
    
    # Resize artwork
    resized_art = img.resize((1920, 1920), Image.Resampling.LANCZOS)
    
    # Composite artwork onto background using the artwork's alpha channel as a mask
    background.paste(resized_art, (0, 0), mask=resized_art.split()[3])
    
    # Save as non-transparent PNG
    background.save(icon_out, format="PNG")
    print(f" Saved opaque 1920x1920 app icon to {icon_out}")

if __name__ == "__main__":
    process_app_assets()

