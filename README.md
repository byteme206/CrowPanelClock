# LitClock Project ESP32
## Overview
This is adapted from examples of other literary clock projects, generally for Raspberry Pi Zero 2W. However, this project is designed to run on an AIO ESP32-S3 wide e-ink display from Elecrow.

Data persistence relies on built-in TFcard support and a FAT32 formatted data partition that holds the location-specific data and wifi credentials, as well as quotations and zip codes database.

## How the Clock Functions
On first boot, the clock will boot up into Captive Portal mode, and it will display instructions on the screen for joining its temporary network to complete configuration. Once joined from your phone or tablet, you will open the camera app and scan the QR code on the clock face. This will open the device to the simple setup form.

From the setup form, you will enter details about your wifi network, which the clock needs to update its time automatically. You will also choose your ZIP code to enable local weather display. Weather is updated every 15 minutes from Open-Meteo.

For every minute of the day, the clock checks its massive database of literary quotes, randomly chooses one that matches the present minute, and updates the clock face to display that quote in which that time appears, with the time emphasized within it.

Once an hour, the clock face will flash momentarily as the clock performs a full screen refresh to clear any e-ink ghosting.

## Installation
1. Insert a TFcard into your computer, and copy the contents of the tfcard folder to the root of that drive.
2. Eject the TFcard and set it aside.
3. Connect the Elecrow panel to your computer with a USB-C power and data cable.
4. Flash the ESP32-S3 with micropython driver firmware: 
5. Using Thonny, install the `urequests` micropython package to your environment.
6. After the ESP32-S3 reboots, it should appear as an external storage device. Copy `main_display_module.py`, `uqr.py`, `CrowPanel.py`, and `main.py` to the external device, then eject it.
6. Unplug the cable from the computer, and plug the clock into a 5v USB-C power adapter. The device should boot within 15 seconds. Follow directions on the screen to connect to the device for first time setup.

## Project layout
|Code File|What it Does|Source|
|---|---|---|
|`main.py`|Contains the core logic for the program.|Me|
|`main_display_module.py`|Contains functions for drawing elements into the dual frame buffers and a custom refresh function that writes the frame buffer to the e-ink panel.|Me|
|`uqr.py`|Helper class for generating a QR code from a URL.|Me|
|`CrowPanel.py`|Custom driver for the CrowPanel_579 display that leverages the dual frame buffer chips.|https://github.com/omiq/crowpanel/blob/main/CrowPanel.py|

|TF Card File|What it Does|
|`config.json`|Holds the wifi and weather settings for the device.|
|`quotes.db`|Holds the database of literary quotes.|
|`zips.csv`|Holds the zip code to lat/long mappings for the weather function.|