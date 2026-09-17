import gc
import network
import time
import ntptime
import socket
import json
from machine import RTC, reset
import urequests

import lib.main_display_module as display_engine

WIDTH = 792
HEIGHT = 272
CONFIG_FILE = "/sd/config.json"
ZIPS_FILE = "/sd/zips.csv"

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            print("Loaded config file.")
            return json.load(f)
    except Exception as e:
        print("Error loading config file, using defaults:", e)
        return {"ssid": "", "password": "", "lat": "47.6062", "lon": "-122.3321", "city": "Seattle", "offset": "-8", "dst": True}

def save_config(lat, lon, city, offset, dst, ssid=None, password=None) -> None:
    config = load_config()
    config["lat"] = lat
    config["lon"] = lon
    config["city"] = city
    config["offset"] = offset
    config["dst"] = dst
    if ssid is not None: config["ssid"] = ssid
    if password is not None: config["password"] = password
        
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
        print("Saved configuration file.")

def init_network_manager(ssid: str, password:str):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if ssid:
        wlan.connect(ssid, password)
        for _ in range(15):
            if wlan.isconnected():
                print("Connected! IP address:", wlan.ifconfig()[0])
                try:
                    ntptime.settime() 
                except:
                    pass
                return True, wlan.ifconfig()[0]
            time.sleep(1)
            
    wlan.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Literary-Clock-Setup", authmode=network.AUTH_OPEN)
    portal_ip = ap.ifconfig()[0]
    print(f"Starting portal on {portal_ip}.")
    return False, portal_ip

def lookup_zip_code(zip_str:str):
    clean_zip = zip_str.strip()
    try:
        with open(ZIPS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(clean_zip):
                    parts = line.strip().split(",")
                    if len(parts) == 6:
                        return parts[1], parts[2], parts[3], parts[4], parts[5]
    except Exception as e:
        print("ZIP file read error:", e)
    return None

def start_web_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(2)
    s.setblocking(False)
    print("Listening on Port 80.")
    return s

def check_web_server(server_socket, is_connected_to_home_wifi) -> None:
    try:
        conn, addr = server_socket.accept()
        request = conn.recv(1024).decode('utf-8')
        
        if "POST /save-all" in request:
            body = request.split("\r\n\r\n")[-1]
            params = dict(u.split("=") for u in body.split("&"))
            ssid = params.get("ssid", "").replace("+", " ")
            password = params.get("password", "").replace("+", " ")
            city = params.get("city", "").replace("+", " ")
            lat = params.get("lat", "")
            lon = params.get("lon", "")
            offset = params.get("offset", "0")
            dst = params.get("dst", False)
            
            save_config(lat, lon, city, offset, dst, ssid, password)
            
            conn.send('HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
            conn.send('<html><body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;text-align:center;padding-top:50px;">'
                      '<h3>Credentials Saved! Rebooting clock...</h3></body></html>')
            conn.close()
            time.sleep(2)
            reset()
            
        elif "POST /search-zip" in request:
            body = request.split("\r\n\r\n")[-1]
            params = dict(u.split("=") for u in body.split("&"))
            zip_input = params.get("zip", "")
            result = lookup_zip_code(zip_input)
            
            if result:
                lat, lon, city, offset, dst = result
                save_config(lat=lat, lon=lon, city=city, offset=offset, dst=dst)
                msg = f'<div class="alert success">ZIP Found! Saved: {city}</div>'
            else:
                msg = '<div class="alert error">ZIP Code not found.</div>'
            
            serve_dashboard(conn, msg, is_connected_to_home_wifi)
            
        elif "GET / " in request or "GET /HTTP" in request:
            serve_dashboard(conn, "", is_connected_to_home_wifi)
            
    except OSError:
        pass

def serve_dashboard(conn, alert_html, is_connected) -> None:
    config = load_config()
    status_badge = '<span style="color:#22c55e;">● Connected</span>' if is_connected else '<span style="color:#eab308;">▲ Portal Mode</span>'
    
    html = f"""HTTP/1.1 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Literary Clock Setup</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; display: flex; justify-content: center; }}
        .card {{ background: #1e293b; max-width: 420px; width: 100%; padding: 25px; border-radius: 12px; }}
        h2 {{ color: #38bdf8; }}
        input[type="text"], input[type="password"] {{ width: 100%; padding: 10px; background: #0f172a; border: 1px solid #475569; color: #fff; margin-bottom: 15px; box-sizing: border-box; }}
        input[type="submit"] {{ width: 100%; padding: 12px; background: #0284c7; border: none; color: #fff; font-weight: bold; cursor: pointer; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Literary Clock Control Panel</h2>
        <div>System Status: {status_badge}</div><br>
        {alert_html}
        <form action="/search-zip" method="POST">
            <input type="text" id="zip" name="zip" placeholder="e.g. 98101" required>
            <input type="submit" value="Search & Apply by ZIP">
        </form>
        <div style="margin-top:20px; border-top:1px solid #334155; padding-top:20px;">
            <form action="/save-all" method="POST">
                <input type="text" id="ssid" name="ssid" value="{config['ssid']}" placeholder="Wi-Fi Name" required>
                <input type="password" id="password" name="password" value="{config['password']}" placeholder="Password" required>
                <input type="text" id="city" name="city" value="{config['city']}" required>
                <input type="text" id="lat" name="lat" value="{config['lat']}" required>
                <input type="text" id="lon" name="lon" value="{config['lon']}" required>
                <input type="text" id="offset" name="offset" value="{config['offset']}" required>
                <input type="submit" value="Save Settings & Reboot">
            </form>
        </div>
    </div>
</body>
</html>
"""
    conn.send(html)
    conn.close()

def fetch_weather(lat=47.6062, lon=-122.3321) -> tuple[str, str]:
    url = f"http://open-meteo.com{lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit"
    try:
        gc.collect()
        response = urequests.get(url, timeout=10)
        data = response.json()
        response.close()
        current = data.get("current_weather", {})
        temp = int(round(current.get("temperature", 0)))
        code = current.get("weather_code", 0)
        weather_map = {0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast", 45: "Foggy", 61: "Light Rain"}
        return f"{temp} F", weather_map.get(code, "Cloudy")
    except Exception:
        return "N/A", "Offline"

# --- Initialization ---
config = load_config()
is_home_wifi, network_ip = init_network_manager(config["ssid"], config["password"])
s = start_web_server()

rtc = RTC()
offset = int(config.get("offset", 0))
temp, condition = "N/A", "Offline"
weather_timer = 15
minute_counter = 60
portal_rendered = False

while True:
    if is_home_wifi:
        now = rtc.datetime()
        hour = now[4]
        minute = now[5]
        
        # Proper rolling mathematical modulo tracking handles daylight adjustments safely
        if config.get("dst", False) and (3 <= now[1] <= 10):
            hour += 1
        local_hour = (hour + offset) % 24
        time_str = f"{local_hour:02d}:{minute:02d}"
        
        if weather_timer >= 15:
            temp, condition = fetch_weather(lat=float(config["lat"]), lon=float(config["lon"]))
            weather_timer = 0

        should_refresh_fully = False
        if minute_counter >= 60:
            should_refresh_fully = True
            minute_counter = 0

        display_engine.update_split_display(time_str, temp, condition, config["city"], should_refresh_fully)
        
        for _ in range(600):
            check_web_server(s, is_home_wifi)
            time.sleep_ms(100)
        weather_timer += 1
        minute_counter += 1
    else:
        # AP Portal loop - ensure we render the screen only ONCE to avoid destroying E-paper particles
        if not portal_rendered:
            portal_url = f"http://{network_ip}"
            display_engine.fb.fill(1)
            
            display_engine.fb.text("[ PORTAL SETUP ACTIVE ]", 30, 40, 0)
            display_engine.fb.text("1. Connect phone to Wi-Fi Network:", 30, 80, 0)
            display_engine.fb.text("   SSID: Literary-Clock-Setup", 30, 105, 0)
            display_engine.fb.text("2. Open browser URL:", 30, 145, 0)
            display_engine.fb.text(f"   URL: {portal_url}", 30, 170, 0)
            display_engine.fb.text("3. Submit form to activate device.", 30, 210, 0)
            
            display_engine.fb.vline(580, 0, HEIGHT, 0)
            display_engine.fb.text("SCAN TO CONFIG", 615, 40, 0)
            
            display_engine.draw_qr_code(display_engine.fb, text_payload=portal_url, start_x=615, start_y=80, pixel_scale=5)
            
            # Flush using official Screen_579 full update methods explicitly
            display_engine.display.show(mode=0)
            portal_rendered = True
            check_web_server(s, is_home_wifi)
            time.sleep_ms(100)
