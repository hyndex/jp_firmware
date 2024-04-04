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

app = Flask(__name__)

HARDWARE_DETAILS_FILE = 'hardware_details.json'
CHARGING_SESSIONS_FILE = 'charging_sessions.csv'
GPIO_PIN_1 = 17  # GPIO pin number for detecting shorting
GPIO_PIN_2 = 18  # GPIO pin number for detecting shorting

# Check if running on Raspberry Pi
def is_raspberry_pi():
    if platform.system() == 'Linux':
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

# Setup pigpio instance if on Raspberry Pi
if is_raspberry_pi():
    pi = pigpio.pi()
else:
    pi = None
    print("Running on a non-Raspberry Pi system. GPIO pin monitoring disabled.")

def check_internet_connection():
    try:
        # Attempt to connect to a well-known server (e.g., Google DNS)
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False

def check_pm2_status():
    try:
        subprocess.check_output(['pm2', 'ping'])
        return True
    except subprocess.CalledProcessError:
        return False

def create_hotspot():
    hardware_details = load_or_generate_hardware_details()
    ssid = hardware_details['hardware_id']
    password = hardware_details.get('password')  # Retrieve the password from hardware details
    if not password:
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))  # Generate a random password if not available
        hardware_details['password'] = password  # Save the password in hardware details
        with open(HARDWARE_DETAILS_FILE, 'w') as f:
            json.dump(hardware_details, f)
    try:
        subprocess.check_output(['nmcli', 'device', 'wifi', 'hotspot', 'con-name', ssid, 'ssid', ssid, 'band', 'bg', 'password', password])
        return True
    except subprocess.CalledProcessError:
        return False

def generate_hardware_details():
    hardware_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))  # Generate a random hardware ID
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))  # Generate a random password
    timestamp = time.time()  # Get the current timestamp
    data = {
        'hardware_id': hardware_id,
        'password': password,  # Include password in hardware details
        'timestamp': timestamp  # Include timestamp in hardware details
    }
    with open(HARDWARE_DETAILS_FILE, 'w') as f:
        json.dump(data, f)
    return data

def load_or_generate_hardware_details():
    if os.path.exists(HARDWARE_DETAILS_FILE):
        with open(HARDWARE_DETAILS_FILE, 'r') as f:
            return json.load(f)
    else:
        return generate_hardware_details()

def load_charging_sessions():
    sessions = []
    if os.path.exists(CHARGING_SESSIONS_FILE):
        with open(CHARGING_SESSIONS_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sessions.append(row)
    return sorted(sessions, key=lambda x: x.get('Transaction ID', ''), reverse=True)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        wifi_ssid = request.form.get('wifi_ssid')
        wifi_password = request.form.get('wifi_password')
        server_url = request.form.get('server_url')
        charger_id = request.form.get('charger_id')

        charger_config = {
            'server_url': server_url,
            'charger_id': charger_id
        }

        with open('./charger.json', 'w') as f:
            json.dump(charger_config, f)

        wifi_status = ''
        if wifi_ssid and wifi_password:
            try:
                subprocess.run(['nmcli', 'device', 'wifi', 'connect', wifi_ssid, 'password', wifi_password], check=True)
                wifi_status = 'WiFi connected successfully!'
            except subprocess.CalledProcessError:
                wifi_status = 'Failed to connect to WiFi. Please check your credentials.'

        return f'{wifi_status} Configuration updated successfully!'
    hardware_details = load_or_generate_hardware_details()
    charging_sessions = load_charging_sessions()
    return render_template('index.html', hardware_details=hardware_details, charging_sessions=charging_sessions)

@app.route('/restart_pm2', methods=['POST'])
def restart_pm2():
    try:
        subprocess.run(['pm2', 'restart', 'all'], check=True)
        return "PM2 processes restarted successfully!"
    except subprocess.CalledProcessError:
        return "Failed to restart PM2 processes."

@app.route('/download_pm2_log', methods=['GET'])
def download_pm2_log():
    pm2_log_file = os.path.expanduser('~/.pm2/logs/main-out.log')  # Update this with the correct path to your PM2 log file
    return send_file(pm2_log_file, as_attachment=True)

# Function to detect GPIO pin shorting and trigger hotspot creation
def detect_short():
    while pi:
        # Check if GPIO pins are shorted
        if pi.read(GPIO_PIN_1) == 0 and pi.read(GPIO_PIN_2) == 0:
            create_hotspot()  # Trigger hotspot creation
            break
        time.sleep(0.1)

if __name__ == '__main__':
    # Start a separate thread to continuously detect GPIO pin shorting if on Raspberry Pi
    if is_raspberry_pi() and pi:
        import threading
        shorting_thread = threading.Thread(target=detect_short)
        shorting_thread.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
