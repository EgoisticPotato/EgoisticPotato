import sys
from pathlib import Path
from PIL import Image

# Ensure scripts directory is in path
sys.path.append(str(Path(__file__).parent))
import config

def load_and_preprocess_image(image_path: Path):
    if not image_path.exists():
        raise FileNotFoundError(f"Headshot not found at {image_path}")
    
    img = Image.open(image_path)
    
    # If the image has an alpha channel, simply convert to RGB (discard alpha) without adding a white background.
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGB')
    elif getattr(config, 'USE_BACKGROUND_REMOVAL', False):
        try:
            from rembg import remove
            print("Removing background with rembg...")
            img = remove(img)
            # Convert the numpy array returned by rembg to a PIL Image
            from PIL import Image as PILImage
            img = PILImage.fromarray(img)
            # Convert to RGB to discard alpha channel after background removal
            img = img.convert('RGB')
        except Exception as e:
            print(f"Warning: rembg failed to import. Skipping background removal. Error: {e}")
    width, height = img.size
    cols = config.PORTRAIT_COLUMNS
    rows = int(cols * (height / width) * 0.48)
    
    # Resize
    img = img.resize((cols, rows), Image.Resampling.LANCZOS)
    
    # Convert to grayscale
    img = img.convert('L')
    
    return img

def image_to_ascii(img):
    ascii_rows = []
    width, height = img.size
    pixels = img.load()
    
    for y in range(height):
        row = ""
        for x in range(width):
            pixel_value = pixels[x, y]
            brightness = (255 - pixel_value) / 255.0
            row += config.get_char_for_brightness(brightness)
        ascii_rows.append(row)
        
    return ascii_rows

def generate_svg(ascii_rows):
    font_path = config.FONT_RAMP_PATH
    if not font_path.exists():
        font_path = config.FONTS_DIR / "JetBrainsMono-Regular.ttf"
        
    try:
        font_b64 = config.load_font_base64(font_path)
        if font_path.suffix == ".ttf":
            font_b64 = font_b64.replace("font/woff2", "font/ttf")
    except Exception as e:
        print(f"Warning: Could not load font: {e}")
        font_b64 = ""
        
    cols = config.PORTRAIT_COLUMNS
    rows = len(ascii_rows)
    
    viewbox_width = config.PORTRAIT_SVG_VIEWBOX_WIDTH
    display_width = config.PORTRAIT_SVG_DISPLAY_WIDTH_PX
    
    font_size = config.FONT_SIZE_PX
    char_width = config.CHAR_WIDTH_EM
    
    svg_height = rows * font_size + font_size
    svg_width = cols * font_size * char_width

    delay = config.TYPING_ANIMATION_DELAY_ROWS
    dur = config.TYPING_ANIMATION_DURATION_PER_ROW

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {viewbox_width} {svg_height}" width="{display_width}px">
'''
    
    if font_b64:
        svg_content += f'''  <defs>
    <style>
      @font-face {{
        font-family: 'JetBrains Mono';
        src: url('{font_b64}');
        font-weight: normal;
        font-style: normal;
      }}
    </style>
  </defs>
'''

    svg_content += f'''  <g font-family="JetBrains Mono, monospace" font-size="{font_size}px" fill="{config.PORTRAIT_FILL_COLOR}" text-anchor="start">
'''

    for i, row_text in enumerate(ascii_rows):
        y_pos = (i + 1) * font_size
        begin_time = i * delay
        
        svg_content += f'''    <clipPath id="clip{i}">
      <rect x="0" y="{y_pos - font_size}" width="0" height="{font_size * 1.5}">
        <animate attributeName="width" from="0" to="{svg_width + font_size}" dur="{dur}s" begin="{begin_time}s" fill="freeze" />
      </rect>
    </clipPath>
    
    <text x="0" y="{y_pos}" clip-path="url(#clip{i})" xml:space="preserve">{row_text}</text>
    
    <!-- Cursor block -->
    <rect x="0" y="{y_pos - font_size*0.8}" width="{font_size * 0.6}" height="{font_size}" fill="{config.PORTRAIT_CURSOR_COLOR}" opacity="0">
      <animate attributeName="x" from="0" to="{svg_width}" dur="{dur}s" begin="{begin_time}s" fill="freeze" />
      <animate attributeName="opacity" values="0; {config.TYPING_CURSOR_OPACITY}; 0" keyTimes="0; 0.1; 1" dur="{dur + 0.1}s" begin="{begin_time}s" fill="freeze" />
    </rect>
'''

    svg_content += '''  </g>
</svg>
'''
    return svg_content

def main():
    print("Loading image...")
    img = load_and_preprocess_image(config.HEADSHOT_PATH)
    
    print("Quantizing to ASCII...")
    ascii_rows = image_to_ascii(img)
    
    print("Generating SVG...")
    svg = generate_svg(ascii_rows)
    
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.PORTRAIT_SVG_PATH
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(svg)
        
    print(f"✅ Success! Generated portrait at {out_path}")
    print(f"Rows: {len(ascii_rows)}, Columns: {config.PORTRAIT_COLUMNS}")
    print(f"Total animation duration: {len(ascii_rows) * config.TYPING_ANIMATION_DELAY_ROWS:.2f}s")

if __name__ == "__main__":
    main()
