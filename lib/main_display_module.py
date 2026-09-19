import gc
from micropython import const
import CrowPanel as eink
from uQR import QRCode
from writer import Writer
import literata as myfont
import literatabold as myfont_bold
import literataitalic as myfont_italic
import roboto as robotofont

# Screen configuration
WIDTH = const(792)
HEIGHT = const(272)
QUOTES_FILE = "/sd/quotes.db"

# Initialize display
display = eink.Screen_579()
fb = display
font_writer = Writer(fb, myfont, verbose=False)
font_writer_bold = Writer(fb, myfont_bold, verbose=False)
font_writer_italic = Writer(fb, myfont_italic, verbose=False)
font_writer_roboto = Writer(fb, robotofont, verbose=False)

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

def render_quote_native(quote: str, target_phrase: str, start_x: int, start_y: int, max_x: int) -> None:
    ''' Render quote using Writer's word-by-word line wrapping. '''
    font_writer.set_clip(row_clip=False, col_clip=False, wrap=True)
    font_writer.set_textpos(fb, start_y, start_x)
    
    # Extract clean target words into a set for exact word matching
    target_words = {w.lower().strip(".,;:!?\"'") for w in target_phrase.split()}
    words = quote.split(" ")

    for i, word in enumerate(words):
        clean_word = word.lower().strip(".,;:!?\"'")
        is_target = clean_word in target_words and clean_word != ""
        writer_to_use = font_writer_bold if is_target else font_writer

        # Check if the word + trailing space will exceed max right boundary
        word_width = writer_to_use.stringlen(word + " ")
        curr_row, curr_col = writer_to_use._getstate().text_row, font_writer._getstate().text_col

        # If adding this word exceeds max_x, wrap to the next line manually at start_x
        if curr_col + word_width > max_x:
            new_row = curr_row + writer_to_use.font.height()
            writer_to_use.set_textpos(fb, new_row, start_x)

        # Print the word
        writer_to_use.printstring(word, invert=True)

        # Print trailing space
        if i < len(words) - 1:
            writer_to_use.printstring(" ", invert=True)

    # Reset clip settings
    font_writer.set_clip()

def draw_weather_icon(condition: str, x: int, y: int, size: int) -> None:
    """
    Renders scalable vector weather icons (Sun, Clouds, Rain, Fog, Snow, Storm)
    inside a bounding box at (x, y) with width/height equal to size.
    """
    c = condition.lower()
    s = size / 100.0  # Scale relative to a 100x100 relative canvas

    def draw_sun(cx, cy, r):
        fb.ellipse(int(cx), int(cy), int(r), int(r), 0, True)
        r_in = int(r + 5 * s)
        r_out = int(r + 14 * s)
        # Cardinal rays
        fb.line(int(cx - r_out), int(cy), int(cx - r_in), int(cy), 0)
        fb.line(int(cx + r_in), int(cy), int(cx + r_out), int(cy), 0)
        fb.line(int(cx), int(cy - r_out), int(cx), int(cy - r_in), 0)
        fb.line(int(cx), int(cy + r_in), int(cx), int(cy + r_out), 0)
        # Diagonal rays
        d_in = int(r_in * 0.707)
        d_out = int(r_out * 0.707)
        fb.line(int(cx - d_out), int(cy - d_out), int(cx - d_in), int(cy - d_in), 0)
        fb.line(int(cx + d_in), int(cy - d_in), int(cx + d_out), int(cy - d_out), 0)
        fb.line(int(cx - d_out), int(cy + d_out), int(cx - d_in), int(cy + d_in), 0)
        fb.line(int(cx + d_in), int(cy + d_out), int(cx + d_out), int(cy + d_in), 0)

    def draw_cloud(cx, cy, width):
        cw = width / 60.0
        # Overlapping cloud bubbles + filled base
        fb.ellipse(int(cx - 15 * cw), int(cy + 2 * cw), int(12 * cw), int(12 * cw), 0, True)
        fb.ellipse(int(cx), int(cy - 8 * cw), int(18 * cw), int(18 * cw), 0, True)
        fb.ellipse(int(cx + 18 * cw), int(cy + 4 * cw), int(13 * cw), int(13 * cw), 0, True)
        fb.fill_rect(int(cx - 22 * cw), int(cy + 2 * cw), int(52 * cw), int(16 * cw), 0)

    # --- Icon Routing ---
    if "clear" in c and "mainly" not in c and "partly" not in c:
        draw_sun(x + 50 * s, y + 50 * s, 22 * s)

    elif "partly" in c or "mainly" in c:
        # Sun behind cloud
        draw_sun(x + 35 * s, y + 35 * s, 16 * s)
        # White background mask behind cloud
        fb.ellipse(int(x + 55 * s), int(y + 60 * s - 6 * 0.8), int(20 * 0.8), int(20 * 0.8), 1, True)
        fb.fill_rect(int(x + 55 * s - 24 * 0.8), int(y + 60 * s), int(56 * 0.8), int(18 * 0.8), 1)
        draw_cloud(x + 55 * s, y + 60 * s, 48 * s)

    elif "rain" in c or "drizzle" in c or "shower" in c:
        draw_cloud(x + 50 * s, y + 38 * s, 55 * s)
        # Angled rain drops
        for rx in (x + 30 * s, x + 44 * s, x + 58 * s, x + 70 * s):
            fb.line(int(rx), int(y + 62 * s), int(rx - 6 * s), int(y + 78 * s), 0)
            fb.line(int(rx + 1), int(y + 62 * s), int(rx - 5 * s), int(y + 78 * s), 0)

    elif "fog" in c or "mist" in c:
        for offset_y in (25 * s, 40 * s, 55 * s, 70 * s):
            fb.fill_rect(int(x + 20 * s), int(y + offset_y), int(60 * s), int(4 * s), 0)

    elif "snow" in c:
        draw_cloud(x + 50 * s, y + 38 * s, 55 * s)
        for sx, sy in ((x + 35 * s, y + 68 * s), (x + 50 * s, y + 75 * s), (x + 65 * s, y + 68 * s)):
            fb.ellipse(int(sx), int(sy), int(3 * s), int(3 * s), 0, True)

    elif "thunder" in c or "storm" in c:
        draw_cloud(x + 50 * s, y + 35 * s, 55 * s)
        pts = [(x + 52 * s, y + 55 * s), (x + 42 * s, y + 70 * s), (x + 48 * s, y + 70 * s), (x + 40 * s, y + 88 * s)]
        for i in range(len(pts) - 1):
            fb.line(int(pts[i][0]), int(pts[i][1]), int(pts[i+1][0]), int(pts[i+1][1]), 0)

    else:  # "cloudy", "overcast", fallback
        draw_cloud(x + 50 * s, y + 48 * s, 65 * s)

def update_split_display(
        time_str, 
        date_str,
        temp, 
        condition, 
        city, 
        full_refresh=False
        ) -> None:
    target_phrase, quote, book, author = find_quote_on_card(time_str)
    fb.fill(1) 
    
    # --- WEATHER SIDEBAR ---
    sidebar_width = 192
    padding = 20

    if hasattr(font_writer_roboto, "stringlen"):
        text_width = font_writer_roboto.stringlen(date_str + "  " + time_str)
    else:
        # Fallback for standard 8px-wide fixed framebuffer fonts
        text_width = len(date_str + "  " + time_str) * 8
        
    time_x = (sidebar_width - text_width) // 2
    time_y = 20  # Vertical offset top margin
    
    # Render centered time string
    font_writer_roboto.set_textpos(fb, time_y, time_x)
    font_writer_roboto.printstring(date_str + " " + time_str, invert=True)

    if hasattr(font_writer_roboto, "stringlen"):
        city_width = font_writer_roboto.stringlen(city[:15])
    else:
        # Fallback for standard 8px-wide fixed framebuffer fonts
        city_width = len(city[:15]) * 8

    city_x = (sidebar_width - city_width) // 2
    font_writer_roboto.set_textpos(fb, 50, city_x)
    font_writer_roboto.printstring(city[:15], invert=True)

    icon_size = (sidebar_width - (padding * 2)) - 24  # Yields 172px width automatically
    icon_x = int((sidebar_width - icon_size) / 2)
    icon_y = 80
    draw_weather_icon(condition, x=icon_x, y=icon_y, size=icon_size)    

    font_writer_roboto.set_textpos(fb, 220, 15)
    font_writer_roboto.printstring(f"Temp: {temp}", invert=True)
    font_writer_roboto.set_textpos(fb, 240, 15)
    font_writer_roboto.printstring(f"Cond: {condition[:18]}", invert=True)
    
    fb.vline(sidebar_width, 0, HEIGHT, 0)
    
    # --- QUOTE CANVAS ---
    render_quote_native(quote, target_phrase, start_x=212, start_y=14, max_x=WIDTH - 20)
    
    footer_text = f"--- {book} ({author})"
    right_margin = 20
    bottom_margin = 15
    footer_width = font_writer_italic.stringlen(footer_text)
    target_col = WIDTH - footer_width - right_margin
    target_row = HEIGHT - font_writer_italic.font.height() - bottom_margin
    
    font_writer_italic.set_textpos(fb, target_row, target_col)
    font_writer_italic.printstring(footer_text, invert=True)
    
    if full_refresh:
        display.show(mode=0) # SCREEN_UPDATE_FULL
    else:
        display.show(mode=2) # SCREEN_UPDATE_FAST