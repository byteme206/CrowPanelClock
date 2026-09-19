# CrowPanel Clock
## Overview
This is adapted from examples of other literary clock projects, generally for Raspberry Pi Zero 2W. However, this project is designed to run on an AIO ESP32-S3 wide e-ink display from Elecrow.

https://www.elecrow.com/crowpanel-esp32-5-79-e-paper-hmi-display-with-272-792-resolution-black-white-color-driven-by-spi-interface.html?srsltid=AfmBOorAEavovHgv6RwpOEVgmnrw2qmFxBe2H_AeXZhIT7Rl1VH7epkI

Data persistence relies on built-in storage (4GB Flash) but you can also insert a microSD card and it will mount to and supplant that mount point. Mounted at /sd is a FAT32 formatted data partition that holds the quotations and zip codes database as well as the system configuration settings.

## How the Clock Functions
On first boot, the clock will be in Captive Portal mode, and it will display instructions on the screen for joining its temporary network to complete configuration. Once joined from your phone or tablet, you will open the camera app and scan the QR code on the clock face. This will open the device to the simple setup form.

On the setup form, enter your 5-digit US postal code and click the Search button. The system will pull in details about your location that it needs to serve up local time and weather. Please enter a valid SSID and network password. CrowPanel clock uses this this connection to sync its time via NTP and to obtain current weather details. Click the Save button at the bottom, and the clock will reboot.

For every minute of the day, the clock checks its massive database of literary quotes, randomly chooses one that matches the present minute, and updates the clock face to display that quote in which that time appears, with the time emphasized within it. Note that for some times of day, there is just no open source quote, and the clock will fall back to the previous minutes in order until it locates a quote. In some cases, there are multiple possibilities for a specific tine of day (looking at you, midnight!). In these cases, the clock randomly chooses one.

Once an hour, the clock face will flash momentarily as the clock performs a full screen refresh to clear any e-ink ghosting.

## Installation
1. Check out this repository to your local system.
2. Connect the Elecrow panel to your computer with a USB-C power and data cable.
3. Flash the ESP32-S3 with micropython driver firmware: 
5. After the ESP32-S3 reboots, it should appear as an external storage device.
6. Using Thonny, install the `urequests` micropython package to your environment.
7. Copy the folders `sd` and `lib`, and the file `main.py` to the root of the external device, then eject it.
8. Unplug the cable from the computer, and plug the clock into a 5v USB-C power adapter. The device should boot within a few seconds. Follow the directions on the screen to connect to the device for first-time setup.
14. Enter your postal code and click "Search and Apply." The system should look up your postal code and fill in the name of your city and the latitude and longitude, which are used to obtain local weather.
15. Enter your WiFi network credentials.
16. Click "Save Settings and Reboot Clock."

## Project details
|SD Card File|What it Does|
|---|---|
|`boot_splash.bin`|Boot splash image.|
|`config.json`|Holds the wifi and location settings for the device after first time setup.|
|`quotes.db`|Holds the database of literary quotes.|
|`zips.csv`|Holds the postal code to lat/long mappings for the weather and DST functions. The example provided is a limited subset of postal codes to save on storage space. Modify as needed for your use case.|

### Postal Code Database Layout
This is a CSV file that maps a postal code to location details, used for easier setup.

|Field #|Label|Purpose|
|---|---|---|
|1|Postal Code|Used as a lookup key for quickly configuring location data.|
|2|Latitude|Used for weather lookup.|
|3|Longitude|Used for weather lookup.|
|4|Locale Name|Name of the associated location.|
|5|UTC Offset|The timezone offset from UTC for this locale.|
|6|DST Observed|A boolean indicating whether or not this locale observes US Daylight Saving Time.|
