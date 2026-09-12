import os
import network
import time
import ntptime
import socket
import json
from machine import RTC, reset
import urequests

import lib.main_display_module as display_engine # Custom module layout wrapper


WIDTH = 792
HEIGHT = 272
CONFIG_FILE = "/sd/config.json"
ZIPS_FILE = "/sd/zips.csv"


def load_config() -> dict:
    ''' Load the configuration details from flash.'''
    try:
        with open(CONFIG_FILE, "r") as f:
            print("Loaded config file.")
            return json.load(f)
    except Exception as e:
        print("Error loading config file, using defaults:", e)
        return {"ssid": "", "password": "", "lat": "47.6062", "lon": "-122.3321", "city": "Seattle", "offset": "-8", "dst": True} # System default

def save_config(lat, lon, city, offset, dst, ssid=None, password=None) -> None:
    ''' Saves config data to flash.'''
    config = load_config()
    config["lat"] = lat
    config["lon"] = lon
    config["city"] = city
    config["offset"] = offset
    config["dst"] = dst
    if ssid is not None:
        config["ssid"] = ssid
    if password is not None:
        config["password"] = password
        
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
        print("Saved configuration file.")

def init_network_manager(ssid: str, password:str):
    ''' Initializes the WiFi radio in station mode but switches to
    Access Point mode if it cannot connect to a WiFi network within
    15 seconds.
    '''
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Try connecting to stored home Wi-Fi if credentials exist
    if ssid:
        wlan.connect(ssid, password)
        
        # Wait up to 15 seconds for network confirmation
        for _ in range(15):
            if wlan.isconnected():
                print("Connected! IP address:", wlan.ifconfig()[0])
                try:
                    ntptime.settime() # Sync system clock via network NTP
                except:
                    pass
                return True, wlan.ifconfig()[0]
            time.sleep(1)
            
    # --- Wi-Fi Failed or Missing: Initialize Captive Access Point Portal ---
    wlan.active(False) # Turn off station mode antenna
    
    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    # Configure local hot-spot parameters (Open network for quick configuration access)
    ap.config(essid="Literary-Clock-Setup", authmode=network.AUTH_OPEN)
    portal_ip = ap.ifconfig()[0] # Default is usually 192.168.4.1 
    print(f"Starting portal on {portal_ip}.")
    return False, portal_ip

def lookup_zip_code(zip_str:str):
    """
    Scans the local dictionary on the TF card to match a 5-digit ZIP.
    zip_str: str, Five-digit zip code.
    Returns: (latitude, longitude, city_name) or None if not found.
    """
    clean_zip = zip_str.strip()
    try:
        with open(ZIPS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(clean_zip):
                    parts = line.strip().split(",")
                    if len(parts) == 6:
                        return parts[1], parts[2], parts[3], parts[4], parts[5] # lat, lon, city, offset, dst
    except Exception as e:
        print("ZIP file read error:", e)
    return None

def start_web_server():
    ''' Initialize the socket listener on port 80.
    '''
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(2)
    s.setblocking(False) # Non-blocking so it doesn't freeze the clock loop
    print("Listening on Port 80.")
    return s

def check_web_server(server_socket, is_connected_to_home_wifi) -> None:
    ''' Check for user interactions via REST calls.
    '''
    try:
        conn, addr = server_socket.accept()
        request = conn.recv(1024).decode('utf-8')
        
        # --- Handle Complete Setup Submission (Wi-Fi + Manual Location) ---
        if "POST /save-all" in request:
            body = request.split("\r\n\r\n")[-1]
            params = dict(u.split("=") for u in body.split("&"))
            
            # Clean and sanitize incoming web forms strings
            ssid = params.get("ssid", "").replace("+", " ")
            password = params.get("password", "").replace("+", " ")
            city = params.get("city", "").replace("+", " ")
            lat = params.get("lat", "")
            lon = params.get("lon", "")
            offset = params.get("offset", "0")
            dst = params.get("dst", False)
            
            save_config(lat, lon, city, ssid, password, offset, dst)
            
            # Serve success message and force hardware reboot
            conn.send('HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
            conn.send('<html><body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;text-align:center;padding-top:50px;">'
                      '<h3>Credentials Saved! Rebooting clock to connect to your network...</h3></body></html>')
            conn.close()
            time.sleep(2)
            reset()
            
        # --- Handle ZIP Lookup Submission ---
        elif "POST /search-zip" in request:
            body = request.split("\r\n\r\n")[-1]
            params = dict(u.split("=") for u in body.split("&"))
            zip_input = params.get("zip", "")
            result = lookup_zip_code(zip_input)
            
            if result:
                lat, lon, city, offset, dst = result
                save_config(lat, lon, city, offset, dst)
                msg = f'<div class="alert success">ZIP Found! Saved: {city} ({lat}, {lon})</div>'
            else:
                msg = '<div class="alert error">ZIP Code not found.</div>'
            
            serve_dashboard(conn, msg, is_connected_to_home_wifi)
            
        elif "GET / " in request or "GET /HTTP" in request:
            serve_dashboard(conn, "", is_connected_to_home_wifi)
            
    except OSError as e:
        print("OS error:", e)
        pass

def serve_dashboard(conn, alert_html, is_connected) -> None:
    ''' Serve the clock configuration user interface web dashboard.
    '''
    config = load_config()
    status_badge = '<span style="color:#22c55e;">● Connected to Home Wi-Fi</span>' if is_connected else '<span style="color:#eab308;">▲ Portal Configuration Mode</span>'
    
    html = f"""HTTP/1.1 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Literary Clock Setup</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; display: flex; justify-content: center; }}
        .card {{ background: #1e293b; max-width: 420px; width: 100%; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
        h2 {{ margin-top: 0; color: #38bdf8; font-size: 22px; }}
        .status {{ font-size: 13px; color: #94a3b8; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #334155; }}
        .section {{ border-top: 1px solid #334155; padding-top: 20px; margin-top: 20px; }}
        label {{ display: block; font-size: 12px; color: #94a3b8; margin-bottom: 5px; font-weight: bold; }}
        input[type="text"], input[type="password"] {{ width: 100%; padding: 10px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: #fff; box-sizing: border-box; margin-bottom: 15px; font-size: 14px; }}
        input:focus {{ border-color: #38bdf8; outline: none; }}
        input[type="submit"] {{ width: 100%; padding: 12px; background: #0284c7; border: none; border-radius: 6px; color: #fff; font-weight: bold; cursor: pointer; font-size: 14px; }}
        input[type="submit"]:hover {{ background: #0369a1; }}
        .alert {{ padding: 12px; border-radius: 6px; font-size: 13px; margin-bottom: 20px; font-weight: 500; }}
        .success {{ background: #064e3b; color: #6ee7b7; border: 1px solid #047857; }}
        .error {{ background: #7f1d1d; color: #fca5a5; border: 1px solid #b91c1c; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Literary Clock Control Panel</h2>
        <div class="status">System Status: {status_badge}</div>
        
        {alert_html}

        <!-- ZIP Code Quick Search Tool -->
        <form action="/search-zip" method="POST">
            <label for="zip">Quick Setup by US ZIP Code</label>
            <input type="text" id="zip" name="zip" placeholder="e.g. 98101" required>
            <input type="submit" value="Search & Apply by ZIP">
        </form>

        <!-- Main Settings Configuration Form -->
        <div class="section">
            <form action="/save-all" method="POST">
                <h3>Network Configuration</h3>
                <label for="ssid">Home Wi-Fi Name (SSID)</label>
                <input type="text" id="ssid" name="ssid" value="{config['ssid']}" placeholder="Your Wi-Fi Network Name" required>
                
                <label for="password">Wi-Fi Password</label>
                <input type="password" id="password" name="password" value="{config['password']}" placeholder="Your Wi-Fi Password" required>

                <h3>Location Settings</h3>
                <label for="city">City Display Label</label>
                <input type="text" id="city" name="city" value="{config['city']}" required>
                
                <label for="lat">Latitude</label>
                <input type="text" id="lat" name="lat" value="{config['lat']}" required>
                
                <label for="lon">Longitude</label>
                <input type="text" id="lon" name="lon" value="{config['lon']}" required>

                <label for="offset">Timezone Offset (e.g., -8 for PST)</label>
                <input type="text" id="offset" name="offset" value="{config['offset']}" required>
                
                <label for="dst">Daylight Saving Time Observed</label>
                <input type="checkbox" id="dst" name="dst" {"checked" if config.get("dst", False) else ""}>
                
                <input type="submit" value="Save Settings & Reboot Clock">
            </form>
        </div>
    </div>
</body>
</html>
"""
    conn.send(html)
    conn.close()

def fetch_weather(lat=47.6062, lon=-122.3321) -> tuple[str, str]:
    """
    Fetch live weather conditions via Open-Meteo API.
    Defaults to Seattle.
    lat: float, latitude.
    lon: float, longitude.
    """
    url = f"http://open-meteo.com?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit"
    try:
        response = urequests.get(url, timeout=10)
        data = response.json()
        response.close()
        
        current = data.get("current_weather", {})
        temp = int(round(current.get("temperature", 0)))
        code = current.get("weathercode", 0)
        
        # Map common WMO weather codes to simple text strings
        weather_map = {0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
                       45: "Foggy", 51: "Light Drizzle", 61: "Light Rain", 71: "Snow"}
        condition = weather_map.get(code, "Cloudy")
        
        return f"{temp} F", condition
    except Exception as e:
        print("Weather update failed:", e)
        return "N/A", "Offline"

def is_leap_year(year) -> bool:
    '''Returns True if the given year is a leap year, otherwise False.'''
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)() 

def days_in_month(year, month) -> int:
    '''Returns the number of days in a given month, accounting for leap years.'''
    if month == 2:
        return 29 if is_leap_year(year) else 28
    elif month in [4, 6, 9, 11]:
        return 30
    else:
        return 31

def get_time_string(offset=0, dst_observed=False) -> str:
    ''' Returns the current time as a formatted string with DST and timezone offset.'''
    rtc = RTC()
    now = rtc.datetime() # (year, month, day, weekday, hour, minute, second, subseconds)
    year, month, day, _, hour, minute, second, _ = now
    if dst_observed:
        offset += 1
    local_hour = (hour + offset) % 24
    return f"{local_hour:02d}:{minute:02d}"


# --- Initialization ---
config = load_config()

is_home_wifi, network_ip = init_network_manager(
    ssid=config["ssid"], 
    password=config["password"]
    )

# Setup server socket binding
s = start_web_server()

rtc = RTC()
offset = int(config.get("offset", 0))
temp, condition = "N/A", "Offline"
weather_timer = 15
minute_counter = 0

while True:
    if is_home_wifi:
        # --- STANDARD OPERATION MODE ---
        now = rtc.datetime() # Returns a tuple: (year, month, day, weekday, hour, minute, second, subseconds)
        hour = now[4] + offset  # Apply timezone offset
        minute = now[5]
        time_str = f"{hour:02d}:{minute:02d}"

        if weather_timer >= 15:
            temp, condition = fetch_weather(lat=config["lat"], lon=config["lon"])
            weather_timer = 0

        should_refresh_fully = False
        if minute_counter >= 60:
            should_refresh_fully = True
            minute_counter = 0 # Reset screen clock

        display_engine.update_split_display(time_str, temp, condition, config["city"], should_refresh_fully)
        
        # Sleep for a minute while checking the background web server for interactions
        for _ in range(600):
            check_web_server(s, is_home_wifi)
            time.sleep_ms(100)
        weather_timer += 1
        minute_counter += 1
    else:
        # --- ACCESS POINT PORTAL CONFIGURATION MODE ---
        portal_url = f"http://{network_ip}"
        
        # Wipe canvas structure clean to uniform white surface
        display_engine.fb.fill(1)
        
        # ----------------------------------------------------
        # LEFT CANVAS PANEL: Step-by-Step Directions
        # ----------------------------------------------------
        display_engine.fb.text("[ PORTAL SETUP ACTIVE ]", 30, 40, 0)
        display_engine.fb.text("1. Connect your phone to Wi-Fi network:", 30, 80, 0)
        display_engine.fb.text("   -> SSID: Literary-Clock-Setup", 30, 105, 0)
        display_engine.fb.text("2. Scan the QR code or open browser URL:", 30, 145, 0)
        display_engine.fb.text(f"   -> URL: {portal_url}", 30, 170, 0)
        display_engine.fb.text("3. Complete the form to reboot the clock.", 30, 210, 0)
        
        # Draw a clean vertical dividing separation line
        display_engine.fb.vline(580, 0, HEIGHT, 0)
        
        # ----------------------------------------------------
        # RIGHT CANVAS PANEL: Scannable QR Component
        # ----------------------------------------------------
        display_engine.fb.text("SCAN TO CONFIG", 615, 40, 0)
        
        # Generate QR targeting the local server URL at position X=615, Y=80
        display_engine.draw_qr_code(display_engine.fb, text_payload=portal_url, start_x=615, start_y=80, pixel_scale=4)
        
        # Push composite array data blocks to Elecrow hardware and execute refresh
        display_engine.portal_mode()
        
        # Continuous server listening socket trap
        while True:
            check_web_server(s, is_home_wifi)
            time.sleep_ms(100)