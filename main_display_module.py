from micropython import const
import CrowPanel as eink
from uqr import QRCode


# Screen configuration
WIDTH = const(792)
HEIGHT = const(272)

# Initialize display
display = eink.Screen_579()
fb = display

def draw_custom_text(text, target_phrase, start_x, start_y, max_width, line_height=20) -> None:
    ''' Break a string into safe chunks to fit the wide 792-pixel 
    screen width, and apply a bold effect by double-rendering 
    target words into the frame buffer.
    text: str, The literary quote to render.
    target_phrase: str, The substring of text we want emphasized.
    start_x: int, Cursor starting position X axis.
    start_y: int, Cursor starting position Y axis.
    max_width: int, Screen position at which to word wrap.
    line_height: int, Line height in pixels.
    '''
    # Splits, wraps, and bolds specific text inline
    words = text.split(" ")
    cursor_x = start_x
    cursor_y = start_y
    
    # Clean the target phrase for uniform comparison
    target_lower = target_phrase.lower().strip()

    for word in words:
        # Check if the word is part of our target time phrase
        clean_word = word.lower().strip(".,;:!?\"'")
        is_bold = clean_word in target_lower and clean_word != ""
        
        # Calculate pixel width estimation (Native font is roughly 8 pixels wide per char)
        word_width = len(word) * 8 + 8 
        
        # Wrap to next line if text hits the display boundary
        if cursor_x + word_width > start_x + max_width:
            cursor_x = start_x
            cursor_y += line_height

        if is_bold:
            # Render standard text
            fb.text(word, cursor_x, cursor_y, 0x0000)
            # Render offset layers to generate a simulated Bold thickness
            fb.text(word, cursor_x + 1, cursor_y, 0x0000)
            fb.text(word, cursor_x, cursor_y + 1, 0x0000)
        else:
            fb.text(word, cursor_x, cursor_y, 0x0000)

        # Advance horizontal printing cursor
        cursor_x += word_width

def draw_weather_icon(condition, x, y) -> None:
    """Draw minimalist vector shapes based on weather text.
    condition: str, Current weather condition.
    x: int, x position to draw icon.
    y: int, y position to draw icon.
    """
    condition = condition.lower()
    
    if "clear" in condition:
        # Sun: Center circle with simple cross beams
        fb.ellipse(x + 20, y + 20, 10, 10, 0x0000, False)
        fb.line(x + 20, y, x + 20, y + 6, 0x0000)      # Top ray
        fb.line(x + 20, y + 34, x + 20, y + 40, 0x0000) # Bottom ray
        fb.line(x, y + 20, x + 6, y + 20, 0x0000)      # Left ray
        fb.line(x + 34, y + 20, x + 40, y + 20, 0x0000) # Right ray
        
    elif "cloudy" in condition or "overcast" in condition:
        # Cloud: Overlapping rectangles and lines forming a silhouette
        fb.fill_rect(x + 5, y + 18, 30, 12, 0x0000)    # Base
        fb.fill_rect(x + 12, y + 8, 16, 16, 0x0000)    # Main puff
        fb.fill_rect(x + 22, y + 12, 10, 10, 0x0000)   # Side puff
        
    elif "rain" in condition or "drizzle" in condition:
        # Rain: A cloud base with diagonal slash drops
        fb.fill_rect(x + 8, y + 8, 24, 10, 0x0000)     # Cloud top
        fb.line(x + 10, y + 24, x + 6, y + 32, 0x0000) # Raindrop 1
        fb.line(x + 20, y + 24, x + 16, y + 32, 0x0000)# Raindrop 2
        fb.line(x + 30, y + 24, x + 26, y + 32, 0x0000)# Raindrop 3
        
    else:
        # Default/Unknown: A clean minimalist box border
        fb.rect(x + 5, y + 5, 30, 30, 0x0000)

def draw_qr_code(fb, text_payload, start_x, start_y, pixel_scale=4):
    """
    Generates a QR code and scales each matrix item onto the e-paper framebuffer.
    With pixel_scale=4, a Version 2 QR code is roughly 100x100 pixels.
    """
    qr = QRCode(version=2)
    matrix = qr.generate(text_payload)
    size = len(matrix)
    
    # Render a clean white protective boundary padding box around the QR area
    fb.fill_rect(start_x - 8, start_y - 8, (size * pixel_scale) + 16, (size * pixel_scale) + 16, 0xFFFF)
    
    # Loop through the grid array and render black structural items
    for row in range(size):
        for col in range(size):
            if matrix[row][col]:
                fb.fill_rect(
                    start_x + (col * pixel_scale), 
                    start_y + (row * pixel_scale), 
                    pixel_scale, 
                    pixel_scale, 
                    0x0000
                )

def update_split_display(time_str, temp_str, condition_str, city_name, force_full_refresh) -> None:
    target_phrase, quote, book, author = find_quote_on_card(time_str)
    fb.fill(0xFFFF) 
    
    # --- WEATHER SIDEBAR (0 to 192 px) ---
    fb.text(time_str, 20, 20, 0x0000)
    fb.text(city_name[:15], 20, 50, 0x0000)
    
    # Draw weather indicator badge 
    draw_weather_icon(condition_str, x=20, y=80)
    
    fb.text(f"Temp: {temp_str}", 20, 140, 0x0000)
    fb.text(condition_str[:18], 20, 160, 0x0000)
    
    fb.vline(192, 0, HEIGHT, 0x0000)
    
    # --- QUOTE CANVAS (192 to 792 px) ---
    draw_custom_text(quote, target_phrase, start_x=212, start_y=40, max_width=560, line_height=24)
    
    footer_text = f"--- {book} ({author})"
    fb.text(footer_text, WIDTH - (len(footer_text) * 8) - 20, HEIGHT - 40, 0x0000)
    
    # --- SMART REFRESH ROUTING ---
    if force_full_refresh:
        display.show(mode=0) # Full refresh, causes screen flash
    else:
        display.show(mode=2) # Partial refresh, fast and no flashing
