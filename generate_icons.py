import os
from PIL import Image

# The complete list of standard iOS and Briefcase icon square sizes (in pixels)
XCODE_ICON_SIZES = [
    20, 29, 40, 58, 60, 76, 80, 87, 
    120, 152, 167, 180, 
    640, 1024, 1280, 1920
]

def generate_contained_icons(source_path: str, output_dir: str, sizes: list[int]) -> None:
    """
    Resizes a source PNG to various square sizes using a 'contain' strategy.
    Keeps the aspect ratio intact and adds transparent padding as needed.
    """
    if not os.path.exists(source_path):
        print(f"Error: Source image not found at '{source_path}'")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Open the source image and ensure it has an alpha channel for transparency
        with Image.open(source_path) as img:
            img = img.convert("RGBA")
            orig_width, orig_height = img.size
            
            for size in sizes:
                # 1. Calculate target dimensions preserving aspect ratio
                ratio = min(size / orig_width, size / orig_height)
                new_width = int(orig_width * ratio)
                new_height = int(orig_height * ratio)
                
                # 2. Resize the original image using high-quality resampling
                # Resampling choice: Lanczos is preferred for high-quality downscaling
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 3. Create a brand new transparent square canvas
                square_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                
                # 4. Calculate centering coordinates
                paste_x = (size - new_width) // 2
                paste_y = (size - new_height) // 2
                
                # 5. Paste the resized image onto the center of the canvas
                square_canvas.paste(resized_img, (paste_x, paste_y), resized_img)
                
                # 6. Save the resulting square icon
                output_filename = f"icon-{size}.png"
                output_filepath = os.path.join(output_dir, output_filename)
                square_canvas.save(output_filepath, "PNG")
                
                print(f"Generated: {output_filename} ({size}x{size} px)")
                
        print(f"\nSuccess! All icons have been generated in: {os.path.abspath(output_dir)}")
        
    except Exception as e:
        print(f"An error occurred during processing: {e}")

if __name__ == "__main__":
    # Path to your high-resolution source icon (e.g., 1024x1024 or higher)
    SOURCE_IMAGE = "assets/custom_icon.png" 
    
    # Target folder where the generated assets will be stored
    OUTPUT_FOLDER = "assets"
    
    generate_contained_icons(SOURCE_IMAGE, OUTPUT_FOLDER, XCODE_ICON_SIZES)
