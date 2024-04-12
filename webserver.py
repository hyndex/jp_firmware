import os
import json
import subprocess
from flask import Flask, request, render_template, flash, redirect, url_for # type: ignore
import threading
import pigpio # type: ignore
import time

# Constants
CHARGER_DETAILS_FILE = 'charger.json'

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

def create_hotspot():
    try:
        subprocess.run(['nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'PiHotspot', 'password', 'raspberry'], check=True)
        print("Hotspot created successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to create hotspot: {e}")
        return False

def close_hotspot():
    # Check if the hotspot is currently active
    try:
        result = subprocess.run(['nmcli', 'con', 'show', '--active'], capture_output=True, text=True)
        if 'PiHotspot' not in result.stdout:
            print("No hotspot is currently active.")
            return True  # Return True since there is no active hotspot to close

        # If active, try to bring it down
        subprocess.run(['nmcli', 'con', 'down', 'PiHotspot'], check=True)
        print("Hotspot closed successfully.")
        return True  # Return True upon successful closure

    except subprocess.CalledProcessError as e:
        print(f"Failed to close hotspot: {e}")
        return False  # Return False if the command failed

    except Exception as e:
        print('Unexpected error when closing hotspot:', e)
        return False  # Return False if an unexpected error occurs

    return True  # Ensuring that the function returns True by default if no conditions are met


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
                flash('WiFi settings updated and connected successfully!', 'success')
                print('WiFi settings updated and connected successfully!')
            else:
                flash('Failed to connect to WiFi.', 'danger')
                print('Failed to connect to WiFi.')
        else:
            flash('Hotspot was not closed; cannot connect to WiFi.', 'danger')
            print('Hotspot was not closed; cannot connect to WiFi.')

        return redirect(url_for('index'))

    charger_details = load_json_file(CHARGER_DETAILS_FILE)
    return render_template('index.html', charger_details=charger_details)

# Button monitoring function
def monitor_emergency_button():
    last_state = pi.read(EMERGENCY_STOP_PIN) if pi else 1
    while True:
        current_state = pi.read(EMERGENCY_STOP_PIN) if pi else 1
        if current_state != last_state:
            if current_state == 0:
                print('current_state',current_state, 'last_state',last_state, 'EMERGENCY_STOP_PIN',EMERGENCY_STOP_PIN)
                # close_hotspot()
                # charger_details = load_json_file(CHARGER_DETAILS_FILE)
                # ssid = charger_details.get('wifi_ssid', '')
                # password = charger_details.get('wifi_password', '')
                # if ssid and password:
                #     connect_to_wifi(ssid, password)
            else:
                # create_hotspot()
                print('current_state',current_state, 'last_state',last_state, 'EMERGENCY_STOP_PIN',EMERGENCY_STOP_PIN)
            last_state = current_state
        time.sleep(0.1)

if __name__ == '__main__':
    if pi:
        threading.Thread(target=monitor_emergency_button, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
