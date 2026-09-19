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
                rtc_synced = False
                for attempt in range(3):
                    try:
                        print(f"Attempting to sync RTC with NTP (Attempt {attempt + 1}/3)...")
                        ntptime.settime()
                        print("RTC successfully set to UTC:", RTC().datetime())
                        rtc_synced = True
                        break
                    except Exception as e:
                        print(f"Failed to sync RTC with NTP (Attempt {attempt + 1}/3)...")
                        print(f"e")
                        time.sleep(1)

                if not rtc_synced:
                    print("Failed to sync RTC with NTP after 3 attempts.")

                return True, wlan.ifconfig()[0]
            time.sleep(1)
            
    wlan.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Literary-Clock-Setup", authmode=network.AUTH_OPEN)
    portal_ip = ap.ifconfig()[0]
    print(f"Starting portal on {portal_ip}.")
    return False, portal_ip

def unquote(string):
    """
    Decodes URL percent-encoded characters and converts '+' to spaces.
    Example: 'P%40ss%2Bw%20rd%21' -> 'P@ss+w rd!'
    """
    # Convert form space '+' back to actual space
    string = string.replace('+', ' ')
    
    parts = string.split('%')
    if len(parts) == 1:
        return string
    
    result = bytearray(parts[0].encode('utf-8'))
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                # Convert the two hex digits following '%' to a byte integer
                code = int(part[:2], 16)
                result.append(code)
                result.extend(part[2:].encode('utf-8'))
            except ValueError:
                # Fallback if invalid hex digits
                result.append(ord('%'))
                result.extend(part.encode('utf-8'))
        else:
            result.append(ord('%'))
            result.extend(part.encode('utf-8'))
            
    return result.decode('utf-8')

def lookup_zip_code(zip_str: str):
    clean_zip = zip_str.strip()
    try:
        with open(ZIPS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.strip().split(",")]
                if len(parts) >= 5 and parts[0] == clean_zip:
                    dst = parts[5] if len(parts) >= 6 else "True"
                    return parts[1], parts[2], parts[3], parts[4], dst
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

def parse_form_data(body) -> dict:
    """Parses x-www-form-urlencoded data into a dictionary with unquoted values."""
    # Example Usage in HTTP handler:
    # request_body = "ssid=Home%20WiFi&password=P%40ss%23word%21"
    # data = parse_form_data(request_body)
    params = {}
    pairs = body.split('&')
    for pair in pairs:
        if '=' in pair:
            key, val = pair.split('=', 1)
            params[unquote(key)] = unquote(val)
    return params

def check_web_server(server_socket, is_connected_to_home_wifi) -> None:
    conn = None
    try:
        conn, addr = server_socket.accept()
    except OSError as e:
        # EAGAIN / EWOULDBLOCK (Errno 11 or 110) means no incoming connection ready; skip quietly
        if e.args[0] in (11, 110, 35):
            return
        print("Accept error:", e)
        return

    try:
        conn.settimeout(1.0)
        request = b""
        # Read until header terminator is found
        while b"\r\n\r\n" not in request and len(request) < 2048:
            chunk = conn.recv(512)
            if not chunk:
                break
            request += chunk

        req_str = request.decode('utf-8', 'ignore')

        body = ""
        if "\r\n\r\n" in req_str:
            body = req_str.split("\r\n\r\n", 1)[1]

        if "POST /search-zip" in req_str:
            params = parse_form_data(body)
            zip_input = params.get("zip", "")
            result = lookup_zip_code(zip_input)

            if result:
                lat, lon, city, offset, dst = result
                curr = load_config()
                save_config(lat=lat, lon=lon, city=city, offset=offset, dst=dst, 
                            ssid=curr.get("ssid"), password=curr.get("password"))
                msg = f'<div class="alert success">ZIP Found! Saved: {city}</div>'
            else:
                msg = '<div class="alert error">ZIP Code not found.</div>'

            serve_dashboard(conn, msg, is_connected_to_home_wifi)

        elif "POST /save-all" in req_str:
            params = parse_form_data(body)
            dst_setting = "dst" in params or str(params.get("dst", "")).lower() in ("true", "1", "yes", "on")
            save_config(
                lat=params.get("lat", ""),
                lon=params.get("lon", ""),
                city=params.get("city", ""),
                offset=params.get("offset", "0"),
                dst=dst_setting,
                ssid=params.get("ssid", ""),
                password=params.get("password", "")
            )

            conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
            conn.sendall(b'<html><body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;text-align:center;padding-top:50px;">'
                         b'<h3>Credentials Saved! Rebooting clock...</h3></body></html>')
            conn.close()
            time.sleep(2)
            reset()

        else:
            serve_dashboard(conn, "", is_connected_to_home_wifi)

    except Exception as e:
        print("Web server handling error:", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
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
                <label style="color:#fff;"><input type="checkbox" name="dst" value="True" {'checked' if config.get('dst') else ''}> Daylight Saving Time Observed</label><br><br>
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
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto&current=weather_code,temperature_2m&temperature_unit=fahrenheit"
    gc.collect()
    try:
        response = urequests.get(url, timeout=10)
        data = response.json()
        response.close()
        current = data.get("current", {})
        temp = int(round(current.get("temperature_2m", 0)))
        code = current.get("weather_code", 0)
        weather_map = {
            0: "Clear", 
            1: "Mainly Clear", 
            2: "Partly Cloudy", 
            3: "Overcast",
            45: "Foggy", 
            48: "Foggy",
            51: "Light Drizzle", 
            53: "Drizzle", 
            55: "Dense Drizzle",
            61: "Light Rain", 
            63: "Moderate Rain", 
            65: "Heavy Rain",
            71: "Slight Snow", 
            73: "Moderate Snow", 
            75: "Heavy Snow",
            80: "Rain Showers", 
            81: "Rain Showers", 
            82: "Heavy Showers",
            95: "Thunderstorm", 
            96: "Thunderstorm", 
            99: "Thunderstorm"
        }
        print(f"Temp: {temp} F")
        print(f"Code: {code}")
        print(f"Condition: {weather_map.get(code, 'Cloudy')}")
        return f"{temp} F", weather_map.get(code, "Cloudy")
    except Exception:
        return "N/A", "Offline"

def is_dst(year, month, day, hour) -> bool:
    """ Accurate US DST Check: 2nd Sunday in March (2 AM) to 1st Sunday in Nov (2 AM) """
    if month < 3 or month > 11:
        return False
    if month > 3 and month < 11:
        return True
    
    # Calculate day of week using Zeller's / Sakamoto's algorithm
    # Returns 0 for Sunday, 1 for Monday, ..., 6 for Saturday
    t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
    y = year - (1 if month < 3 else 0)
    dow = (y + y // 4 - y // 100 + y // 400 + t[month - 1] + day) % 7
    
    # Day of the month for the most recent Sunday
    sunday = day - dow
    
    if month == 3:
        # DST starts 2nd Sunday in March at 2:00 AM (Day 8-14)
        return sunday >= 8 and (day > sunday or hour >= 2)
    
    if month == 11:
        # DST ends 1st Sunday in Nov at 2:00 AM (Day 1-7)
        return sunday < 1 or (day == sunday and hour < 1)
    
    return False


# --- Initialization ---
config = load_config()
rtc = RTC()
is_home_wifi, network_ip = init_network_manager(config["ssid"], config["password"])
s = start_web_server()
offset = int(float(config.get("offset", 0)))
temp, condition = "N/A", "Offline"
weather_timer = 15
minute_counter = 60
portal_rendered = False

while True:
    if is_home_wifi:
        try:
            utc_offset = int(float(config.get("offset", -8))) # Default to PST
        except ValueError:
            utc_offset = -8  # Default to PST

        dst_config = config.get("dst", True)
        if isinstance(dst_config, str):
            dst_config = dst_config.lower() in ("true", "1", "yes")

        # Convert RTC UTC time to UTC epoch
        utc_epoch = time.time()
        
        # Approximate standard local time to evaluate DST rule in local context
        standard_local_epoch = utc_epoch + (utc_offset * 3600)
        st_time = time.localtime(standard_local_epoch)
        st_year, st_month, st_day, st_hour = st_time[0], st_time[1], st_time[2], st_time[3]

        # Calculate DST shift based on local standard time
        dst_adj = 1 if (dst_config and is_dst(st_year, st_month, st_day, st_hour)) else 0
        total_offset = utc_offset + dst_adj

        # Final accurate local time
        local_epoch = utc_epoch + (total_offset * 3600)
        local_time = time.localtime(local_epoch)
        local_hour = local_time[3]
        local_minute = local_time[4]
        time_str = f"{local_hour:02d}:{local_minute:02d}"
        
        if weather_timer >= 15:
            temp, condition = fetch_weather(lat=float(config["lat"]), lon=float(config["lon"]))
            weather_timer = 0

        should_refresh_fully = False
        if minute_counter >= 60:
            should_refresh_fully = True
            minute_counter = 0

        display_engine.update_split_display(
            time_str=time_str, 
            date_str=f"{local_time[1]:02d}/{local_time[2]:02d}/{local_time[0]}",
            temp=temp, 
            condition=condition, 
            city=config["city"], 
            full_refresh=should_refresh_fully
        )
        
        for _ in range(600):
            check_web_server(s, is_home_wifi)
            time.sleep_ms(100)
        weather_timer += 1
        minute_counter += 1
    else:
        # AP Portal loop - render display ONCE
        if not portal_rendered:
            portal_url = f"http://{network_ip}"
            display_engine.fb.fill(1)

            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 40, 30)
            display_engine.font_writer_roboto.printstring("[ Literary Clock Setup ]", invert=True)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 80, 30)
            display_engine.font_writer_roboto.printstring("1. Connect phone to Wi-Fi Network:", invert=True)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 105, 30)
            display_engine.font_writer_roboto.printstring("   SSID: Literary-Clock-Setup", invert=True)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 145, 30)
            display_engine.font_writer_roboto.printstring("2. Open browser URL or scan QRCode:", invert=True)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 170, 30)
            display_engine.font_writer_roboto.printstring(f"   URL: {portal_url}", invert=True)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 210, 30)
            display_engine.font_writer_roboto.printstring("3. Submit form to activate device.", invert=True)
            display_engine.fb.vline(580, 0, HEIGHT, 0)
            display_engine.font_writer_roboto.set_textpos(display_engine.fb, 40, 615)
            display_engine.font_writer_roboto.printstring("SCAN TO CFG", invert=True)
            display_engine.draw_qr_code(display_engine.fb, text_payload=portal_url, start_x=615, start_y=80, pixel_scale=6)
            display_engine.display.show(mode=0)
            portal_rendered = True

        # Keep processing HTTP requests continuously in AP mode
        check_web_server(s, is_home_wifi)
        time.sleep_ms(50)
    