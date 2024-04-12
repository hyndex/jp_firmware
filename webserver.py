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
    try:
        subprocess.run(['nmcli', 'con', 'down', 'PiHotspot'], check=True)
        print("Hotspot closed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to close hotspot: {e}")


def connect_to_wifi(ssid, password):
    try:
        # Disconnect the current connection on wlan0
        result = subprocess.run(['nmcli', 'device', 'disconnect', 'wlan0'], check=True, capture_output=True, text=True)
        print("Disconnect output:", result.stdout)  # Printing output of disconnect command
        print("Disconnect error:", result.stderr)  # Printing error of disconnect command
        
        # Connect to the specified WiFi network
        result = subprocess.run(['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password], check=True, capture_output=True, text=True)
        print("Connect output:", result.stdout)  # Printing output of connect command
        print("Connect error:", result.stderr)  # Printing error of connect command
        
        return True
    except subprocess.CalledProcessError as e:
        print("Error occurred:", e)  # Printing the exception message
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
                close_hotspot()
                charger_details = load_json_file(CHARGER_DETAILS_FILE)
                ssid = charger_details.get('wifi_ssid', '')
                password = charger_details.get('wifi_password', '')
                if ssid and password:
                    connect_to_wifi(ssid, password)
            else:
                create_hotspot()
            last_state = current_state
        time.sleep(0.1)

if __name__ == '__main__':
    if pi:
        threading.Thread(target=monitor_emergency_button, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
