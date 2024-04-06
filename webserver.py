import csv
from flask import Flask, request, render_template, send_file
import json
import subprocess
import os
import random
import string
import socket
import time
import platform
import threading
from datetime import datetime, timedelta
from flask import Flask, request, render_template, jsonify

if platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model'):
    import pigpio

app = Flask(__name__)

HARDWARE_DETAILS_FILE = 'hardware_details.json'
CHARGING_SESSIONS_FILE = 'charging_sessions.csv'
EMERGENCY_STOP_PIN1 = 5  # Output GPIO pin number
EMERGENCY_STOP_PIN2 = 6  # Input GPIO pin number for the emergency stop button
button_press_times = []  # To track the timestamps of the emergency button presses

def is_raspberry_pi():
    """Check if running on a Raspberry Pi."""
    if platform.system() == 'Linux':
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

def get_current_ssid():
    """Retrieve the SSID of the currently connected Wi-Fi network."""
    try:
        ssid = subprocess.check_output("iwgetid -r", shell=True).decode().strip()
        return ssid
    except subprocess.CalledProcessError:
        return None

def connect_to_wifi(ssid, password):
    """Connect to a Wi-Fi network."""
    try:
        subprocess.check_call(['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password], timeout=30)
        return True
    except subprocess.CalledProcessError:
        return False



if is_raspberry_pi():
    pi = pigpio.pi()
    if not pi.connected:
        pi = None
        print("Running on a non-Raspberry Pi system or pigpio daemon is not running. GPIO pin monitoring disabled.")
else:
    pi = None
    print("Running on a non-Raspberry Pi system. GPIO pin monitoring disabled.")

def setup_emergency_stop_pins():
    """Set up GPIO pins for emergency stop mechanism."""
    if pi:
        pi.set_mode(EMERGENCY_STOP_PIN1, pigpio.OUTPUT)
        pi.write(EMERGENCY_STOP_PIN1, 0)  # Initially LOW
        pi.set_mode(EMERGENCY_STOP_PIN2, pigpio.INPUT)
        pi.set_pull_up_down(EMERGENCY_STOP_PIN2, pigpio.PUD_UP)  # Pull-up

def monitor_emergency_button():
    """Monitor the emergency button and trigger hotspot creation if pressed thrice within 10 seconds."""
    global button_press_times
    if pi:
        while True:
            if pi.read(EMERGENCY_STOP_PIN2) == 0:  # Active LOW
                button_press_times.append(datetime.now())
                # Filter presses within the last 10 seconds
                button_press_times = [time for time in button_press_times if time > datetime.now() - timedelta(seconds=10)]
                if len(button_press_times) >= 3:
                    create_hotspot()
                    button_press_times.clear()  # Clear after creating hotspot
                while pi.read(EMERGENCY_STOP_PIN2) == 0:
                    time.sleep(0.1)  # Debounce
            time.sleep(0.1)

def check_internet_connection():
    """Check if there is an internet connection."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False

@app.route('/wifi_networks', methods=['GET'])
def wifi_networks():
    """Endpoint to list available Wi-Fi networks."""
    try:
        networks = subprocess.check_output(['nmcli', '-t', '-f', 'SSID', 'device', 'wifi', 'list']).decode('utf-8').split('\n')
        networks = [net.strip() for net in networks if net]  # Remove empty entries
        return jsonify(networks)
    except subprocess.CalledProcessError:
        return jsonify([]), 500

@app.route('/connect_wifi', methods=['POST'])
def connect_wifi():
    new_ssid = request.form.get('ssid')
    password = request.form.get('password')
    original_ssid = get_current_ssid()

    if connect_to_wifi(new_ssid, password):
        # Wait for a moment to verify connectivity
        time.sleep(10)
        if check_internet_connection():
            return jsonify({"success": True, "message": f"Connected successfully to {new_ssid}."})
        else:
            # Attempt to rollback
            if original_ssid and connect_to_wifi(original_ssid, ""):
                return jsonify({"success": False, "message": "Failed to connect to new network. Rolled back to the original network."})
            else:
                return jsonify({"success": False, "message": "Failed to connect to new network and failed to rollback."})
    else:
        return jsonify({"success": False, "message": "Failed to initiate connection to new network."})



def check_pm2_status():
    """Check if pm2 process manager is running."""
    try:
        subprocess.check_output(['pm2', 'ping'])
        return True
    except subprocess.CalledProcessError:
        return False

def create_hotspot():
    """Create a WiFi hotspot."""
    hardware_details = load_or_generate_hardware_details()
    ssid = hardware_details['hardware_id']
    password = hardware_details.get('password')
    if not password:
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        hardware_details['password'] = password
        with open(HARDWARE_DETAILS_FILE, 'w') as f:
            json.dump(hardware_details, f)
    try:
        subprocess.check_output(['nmcli', 'device', 'wifi', 'hotspot', 'con-name', ssid, 'ssid', ssid, 'band', 'bg', 'password', password])
        return True
    except subprocess.CalledProcessError:
        return False

def generate_hardware_details():
    """Generate and save new hardware details."""
    hardware_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    timestamp = time.time()
    data = {
        'hardware_id': hardware_id,
        'password': password,
        'timestamp': timestamp
    }
    with open(HARDWARE_DETAILS_FILE, 'w') as f:
        json.dump(data, f)
    return data

def load_or_generate_hardware_details():
    """Load or generate hardware details as needed."""
    if os.path.exists(HARDWARE_DETAILS_FILE):
        with open(HARDWARE_DETAILS_FILE, 'r') as f:
            return json.load(f)
    else:
        return generate_hardware_details()

def load_charging_sessions():
    """Load charging session data."""
    sessions = []
    if os.path.exists(CHARGING_SESSIONS_FILE):
        with open(CHARGING_SESSIONS_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sessions.append(row)
    return sorted(sessions, key=lambda x: x.get('Transaction ID', ''), reverse=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Handle the landing page and form submissions."""
    if request.method == 'POST':
        # Process form data and update configurations
        return "Configuration updated successfully!"
    else:
        # Display the configuration page
        hardware_details = load_or_generate_hardware_details()
        charging_sessions = load_charging_sessions()
        return render_template('index.html', hardware_details=hardware_details, charging_sessions=charging_sessions)

if __name__ == '__main__':
    setup_emergency_stop_pins()
    if is_raspberry_pi() and pi:
        emergency_button_thread = threading.Thread(target=monitor_emergency_button)
        emergency_button_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
