import os
import json
import subprocess
from flask import Flask, request, render_template, flash, redirect, url_for # type: ignore
import threading
import pigpio # type: ignore
import time

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Constants
CHARGER_DETAILS_FILE = 'charger.json'
HOTSPOT_ACTIVE = False  # Global variable to track hotspot state


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Setup for Raspberry Pi GPIO
def is_raspberry_pi():
    try:
        with open('/proc/device-tree/model', 'r') as file:
            return 'Raspberry Pi' in file.read()
    except FileNotFoundError:
        return False

pi = pigpio.pi() if is_raspberry_pi() and pigpio.pi().connected else None
EMERGENCY_STOP_PIN = 5

if pi:
    pi.set_mode(EMERGENCY_STOP_PIN, pigpio.INPUT)
    pi.set_pull_up_down(EMERGENCY_STOP_PIN, pigpio.PUD_DOWN)

# Utility functions
def load_json_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return json.load(file)
    return {}

def save_json_file(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# def create_hotspot():
#     try:
#         subprocess.run(['nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'Joulepoint-Charger-Hotspot', 'password', 'raspberry'], check=True)
#         print("Hotspot created successfully.")
#         return True
#     except subprocess.CalledProcessError as e:
#         print(f"Failed to create hotspot: {e}")
#         return False

def create_hotspot():
    global HOTSPOT_ACTIVE
    if not HOTSPOT_ACTIVE:
        try:
            subprocess.run(['nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'Joulepoint-Charger-Hotspot', 'password', 'raspberry'], check=True)
            print("Hotspot created successfully.")
            HOTSPOT_ACTIVE = True
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create hotspot: {e}")
    else:
        print("Hotspot already active.")
    return False


# def close_hotspot():
#     # Check if the hotspot is currently active
#     try:
#         result = subprocess.run(['nmcli', 'con', 'show', '--active'], capture_output=True, text=True)
#         if 'Joulepoint-Charger-Hotspot' not in result.stdout:
#             print("No hotspot is currently active.")
#             return True  # Return True since there is no active hotspot to close

#         # If active, try to bring it down
#         subprocess.run(['nmcli', 'con', 'down', 'Joulepoint-Charger-Hotspot'], check=True)
#         print("Hotspot closed successfully.")
#         return True  # Return True upon successful closure

#     except subprocess.CalledProcessError as e:
#         print(f"Failed to close hotspot: {e}")
#         return False  # Return False if the command failed

#     except Exception as e:
#         print('Unexpected error when closing hotspot:', e)
#         return False  # Return False if an unexpected error occurs

#     return True  # Ensuring that the function returns True by default if no conditions are met

def close_hotspot():
    global HOTSPOT_ACTIVE
    if HOTSPOT_ACTIVE:
        try:
            subprocess.run(['nmcli', 'con', 'down', 'Joulepoint-Charger-Hotspot'], check=True)
            print("Hotspot closed successfully.")
            HOTSPOT_ACTIVE = False
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to close hotspot: {e}")
            return False
    else:
        print("No hotspot is currently active.")
        return True


def connect_to_wifi(ssid, password):
    try:
        # Ensure that the wlan0 interface is managed and up
        subprocess.run(['nmcli', 'device', 'set', 'wlan0', 'managed', 'yes'], check=True)
        subprocess.run(['ip', 'link', 'set', 'wlan0', 'up'], check=True)

        # Force a WiFi rescan to ensure fresh network data
        subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], check=True)
        
        # Disconnect any existing connection on wlan0 to avoid conflicts
        # subprocess.run(['nmcli', 'device', 'disconnect', 'wlan0'], check=True)
        # print("Disconnected wlan0 successfully.")

        # Connect to the specified WiFi network
        connect_command = ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password]
        result = subprocess.run(connect_command, check=True, capture_output=True, text=True)
        print("Connected successfully to WiFi network.")
        print("Output:", result.stdout)
        return True

    except subprocess.CalledProcessError as e:
        # Check the error output for more specific issues
        print("Failed to execute nmcli command:", str(e))
        print("Error output:", e.stderr)

        if 'permission denied' in e.stderr.lower():
            print("Error: Permission denied. Check if the script has appropriate privileges.")
        elif 'no network with ssid' in e.stderr.lower():
            print("Error: No network with SSID '{}' found. Ensure the SSID is correct and in range.".format(ssid))
        elif 'secrets were required, but not provided' in e.stderr.lower():
            print("Error: Incorrect password provided.")
        elif 'device is not ready' in e.stderr.lower():
            print("Error: Device wlan0 is not ready. Check the device status with 'nmcli device status'.")
        elif 'connection activation failed' in e.stderr.lower():
            print("Error: Connection activation failed. The device may be busy or unable to connect to the specified network.")
        return False

    except subprocess.TimeoutExpired:
        print("Error: Connection attempt timed out.")
        return False

    except Exception as e:
        print("An unexpected error occurred:", str(e))
        return False

# Flask Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        ssid = request.form['wifi_ssid']
        password = request.form['wifi_password']
        server_url = request.form['server_url']
        charger_id = request.form['charger_id']

        # Save the new settings
        save_json_file(CHARGER_DETAILS_FILE, {
            'wifi_ssid': ssid,
            'wifi_password': password,
            'server_url': server_url,
            'charger_id': charger_id
        })

        # Update network connection
        if close_hotspot():
            if connect_to_wifi(ssid, password):
                print('WiFi settings updated and connected successfully!')
            else:
                print('Failed to connect to WiFi.')
        else:
            print('Hotspot was not closed; cannot connect to WiFi.')

        return redirect(url_for('index'))

    charger_details = load_json_file(CHARGER_DETAILS_FILE)
    return render_template('index.html', charger_details=charger_details)


# Button monitoring function
def monitor_emergency_button():
    global HOTSPOT_ACTIVE
    last_state = pi.read(EMERGENCY_STOP_PIN) if pi else 1
    debounce_time = 0.1  # 100 milliseconds

    while True:
        current_state = pi.read(EMERGENCY_STOP_PIN) if pi else 1
        time.sleep(0.01)  # Short sleep to reduce CPU load

        # Read again after a short delay to confirm the state
        confirmed_state = pi.read(EMERGENCY_STOP_PIN) if pi else 1
        if confirmed_state == current_state and current_state != last_state:
            if current_state == 0:  # Assuming 0 is pressed state
                print('HOTSPOT ON current_state', current_state, 'last_state', last_state, 'EMERGENCY_STOP_PIN', EMERGENCY_STOP_PIN)
                create_hotspot()
            elif current_state == 1:  # Assuming 1 is released state
                print('HOTSPOT OFF current_state', current_state, 'last_state', last_state, 'EMERGENCY_STOP_PIN', EMERGENCY_STOP_PIN)
                close_hotspot()
                charger_details = load_json_file(CHARGER_DETAILS_FILE)
                if connect_to_wifi(charger_details['wifi_ssid'], charger_details['wifi_password']):
                    print('WiFi settings updated and connected successfully!')
                else:
                    print('Failed to connect to WiFi.')
                print('WiFi settings updated and connected successfully!', charger_details)
            last_state = current_state  # Update last_state only after handling the change
            time.sleep(debounce_time)  # Debounce delay


if __name__ == '__main__':
    if pi:
        threading.Thread(target=monitor_emergency_button, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
