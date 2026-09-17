import gc
from micropython import const
import CrowPanel as eink
from uQR import QRCode
from writer import Writer
import garamond as myfont

# Screen configuration
WIDTH = const(792)
HEIGHT = const(272)
QUOTES_FILE = "/sd/quotes.db"

# Initialize display
display = eink.Screen_579()
fb = display
font_writer = Writer(fb, myfont, verbose=False)

def draw_qr_code(fb, text_payload, start_x, start_y, pixel_scale=4):
    """
    Generates a compliant QR code and scales each matrix item onto the e-paper framebuffer.
    """
    gc.collect()  
    qr = QRCode(version=2, error_correction=1, border=0)
    qr.add_data(text_payload)
    
    matrix = qr.get_matrix() 
    size = len(matrix)
    qr_side = size * pixel_scale
    
    # Render a clean white protective quiet zone border (1 = White)
    fb.fill_rect(start_x - 8, start_y - 8, qr_side + 16, qr_side + 16, 1)
    
    # Loop through the grid array
    for row in range(size):
        for col in range(size):
            if matrix[row][col]:
                fb.fill_rect(
                    start_x + (col * pixel_scale), 
                    start_y + (row * pixel_scale), 
                    pixel_scale, 
                    pixel_scale, 
                    0 # 0 = Black on CrowPanel
                )

def find_quote_on_card(time_str:str) -> tuple[str, str, str, str]:
    ''' Search the quotes database on the mounted TF card for one
    matching the current system time.
    '''
    try:
        with open(QUOTES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(time_str):
                    parts = line.strip().split("|")
                    if len(parts) == 5:
                        return parts[1], parts[2], parts[3], parts[4]
    except Exception:
        pass
    return "", "Time flies like an arrow.", "Unknown Author", f"({time_str})"

def draw_custom_text(text, target_phrase, start_x, start_y, max_width, font_writer) -> None:
    ''' Break a string into safe chunks to fit the wide 792-pixel screen width, 
    leveraging the Writer framework's native proportional width detection.
    '''
    words = text.split(" ")
    cursor_x = start_x
    cursor_y = start_y
    target_lower = target_phrase.lower().strip()
    line_height = font_writer.font.height() + 6

    for word in words:
        clean_word = word.lower().strip(".,;:!?\"'")
        is_bold = clean_word in target_lower and clean_word != ""
        
        # Leverage Peter Hinch's writer stringlen system minus current cursor math
        # to calculate true pixel dimension metrics dynamically
        word_width = font_writer.stringlen(word) - font_writer._getstate().text_col
        
        if cursor_x + word_width > start_x + max_width:
            cursor_x = start_x
            cursor_y += line_height

        if is_bold:
            font_writer.set_textpos(fb, cursor_y, cursor_x)
            font_writer.printstring(word)
            # Simulated Bold offset layers
            font_writer.set_textpos(fb, cursor_y + 1, cursor_x)
            font_writer.printstring(word)
            font_writer.set_textpos(fb, cursor_y, cursor_x + 1)
            font_writer.printstring(word)
        else:
            font_writer.set_textpos(fb, cursor_y, cursor_x)
            font_writer.printstring(word)

        cursor_x += (word_width + 6) # Add padding space between layout words

def draw_weather_icon(condition, x, y) -> None:
    condition = condition.lower()
    if "clear" in condition:
        fb.ellipse(x + 20, y + 20, 10, 10, 0, False)
        fb.line(x + 20, y, x + 20, y + 6, 0)      
        fb.line(x + 20, y + 34, x + 20, y + 40, 0) 
        fb.line(x, y + 20, x + 20, y + 20, 0)      
        fb.line(x + 34, y + 20, x + 40, y + 20, 0) 
    elif "cloudy" in condition or "overcast" in condition:
        fb.fill_rect(x + 5, y + 18, 30, 12, 0)    
        fb.fill_rect(x + 12, y + 8, 16, 16, 0)    
        fb.fill_rect(x + 22, y + 12, 10, 10, 0)   
    elif "rain" in condition or "drizzle" in condition:
        fb.fill_rect(x + 8, y + 8, 24, 10, 0)     
        fb.line(x + 10, y + 24, x + 6, y + 32, 0) 
        fb.line(x + 20, y + 24, x + 16, y + 32, 0)
        fb.line(x + 30, y + 24, x + 26, y + 32, 0)
    else:
        fb.rect(x + 5, y + 5, 30, 30, 0)

def update_split_display(time_str, temp_str, condition_str, city_name, force_full_refresh) -> None:
    target_phrase, quote, book, author = find_quote_on_card(time_str)
    fb.fill(1) 
    
    # --- WEATHER SIDEBAR ---
    font_writer.set_textpos(fb, 20, 15)
    font_writer.printstring(time_str)
    
    font_writer.set_textpos(fb, 50, 15)
    font_writer.printstring(city_name[:15])
    
    draw_weather_icon(condition_str, x=20, y=80)
    
    font_writer.set_textpos(fb, 140, 20)
    font_writer.printstring(f"Temp: {temp_str}")
    
    font_writer.set_textpos(fb, 160, 20)
    font_writer.printstring(f"Cond: {condition_str[:18]}")
    
    fb.vline(192, 0, HEIGHT, 0)
    
    # --- QUOTE CANVAS ---
    draw_custom_text(quote, target_phrase, start_x=212, start_y=30, max_width=560, font_writer=font_writer)
    
    footer_text = f"--- {book} ({author})"
    target_row = HEIGHT - 40
    # Safe fallback positioning logic
    target_col = WIDTH - 350
    font_writer.set_textpos(fb, target_row, target_col)
    font_writer.printstring(footer_text)
    
    if force_full_refresh:
        display.show(mode=0) # SCREEN_UPDATE_FULL
    else:
        display.show(mode=1) # SCREEN_UPDATE_FAST (Mode 1 gives optimized fast diffing updates)
