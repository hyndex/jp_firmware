import csv
from flask import Flask, request, render_template, send_file, send_from_directory
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
CHARGER_DETAILS_FILE = 'charger.json'
EMERGENCY_STOP_PIN = 5  # Output GPIO pin number
button_press_times = []  # To track the timestamps of the emergency button presses
hotspot_created = False  # Track if the hotspot has already been created

def setup_emergency_stop_pin():
    """Configure the GPIO pin for the emergency stop button."""
    if pi:
        pi.set_mode(EMERGENCY_STOP_PIN, pigpio.INPUT)
        pi.set_pull_up_down(EMERGENCY_STOP_PIN, pigpio.PUD_DOWN)  # Use internal pull-down resistor

button_press_times = []


@app.route('/download_charging_sessions')
def download_charging_sessions():
    """Serve the charging sessions CSV file for download."""
    directory = os.getcwd()  # Get the current working directory
    return send_from_directory(directory=directory,
                               path=CHARGING_SESSIONS_FILE,
                               as_attachment=True)


def load_charger_details():
    """Load charger details from JSON file."""
    if os.path.exists(CHARGER_DETAILS_FILE):
        with open(CHARGER_DETAILS_FILE, 'r') as file:
            return json.load(file)
    return {"server_url": "", "charger_id": "", "wifi_ssid": "", "wifi_password": ""}


def save_charger_details(server_url, charger_id, wifi_ssid, wifi_password):
    """Save charger details to JSON file."""
    data = {
        "server_url": server_url, 
        "charger_id": charger_id,
        "wifi_ssid": wifi_ssid,
        "wifi_password": wifi_password
    }
    with open(CHARGER_DETAILS_FILE, 'w') as file:
        json.dump(data, file)


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


def close_hotspot_and_reconnect(interface='wlan0', original_ssid='', original_password=''):
    """Closes the created hotspot and reconnects to the original Wi-Fi network."""
    try:
        # Disconnect the hotspot
        subprocess.run(['nmcli', 'connection', 'delete', 'hotspot'], check=True)
        print("Hotspot connection deleted.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to delete hotspot connection: {e}")

    # Attempt to reconnect to the original Wi-Fi network
    if original_ssid and original_password:
        connect_success = connect_to_wifi(original_ssid, original_password)
        if connect_success:
            print(f"Reconnected to original network {original_ssid}.")
        else:
            print("Failed to reconnect to original network.")
    else:
        print("No original network details provided.")

    # Ensure the Wi-Fi device is turned on
    subprocess.run(['nmcli', 'radio', 'wifi', 'on'], check=True)


if is_raspberry_pi():
    pi = pigpio.pi()
    if not pi.connected:
        pi = None
        print("Running on a non-Raspberry Pi system or pigpio daemon is not running. GPIO pin monitoring disabled.")
else:
    pi = None
    print("Running on a non-Raspberry Pi system. GPIO pin monitoring disabled.")



# def monitor_emergency_button():
#     """Monitor the emergency button and perform actions based on its state."""
#     global hotspot_created
#     if pi:
#         last_button_state = pi.read(EMERGENCY_STOP_PIN)
#         while True:
#             current_button_state = pi.read(EMERGENCY_STOP_PIN)
#             # Detect switch from off to on
#             if current_button_state == 1 and last_button_state == 0:
#                 print("Switch turned on.")
#                 if not hotspot_created:
#                     print("Creating hotspot.")
#                     create_hotspot_success = create_hotspot()
#                     if create_hotspot_success:
#                         hotspot_created = True
#                     else:
#                         print("Failed to create hotspot.")
#             # Detect switch from on to off
#             elif current_button_state == 0 and last_button_state == 1:
#                 print("Switch turned off.")
#                 hotspot_created = False  # Reset the state to allow hotspot creation again
#                 charger_details = load_charger_details()
#                 close_hotspot_and_reconnect(interface='wlan0', original_ssid=charger_details['wifi_ssid'],original_password=charger_details['wifi_password'])
                
#             last_button_state = current_button_state
#             time.sleep(5)  # Check button state every 100 ms


def monitor_emergency_button():
    """Monitor the emergency button and perform actions based on its state."""
    global hotspot_created
    if pi:
        last_button_state = pi.read(EMERGENCY_STOP_PIN)
        while True:
            current_button_state = pi.read(EMERGENCY_STOP_PIN)
            # Detect switch from off to on (button released)
            if current_button_state == 0 and last_button_state == 1:
                print("Button released.")
                if not hotspot_created:
                    print("Creating hotspot.")
                    create_hotspot_success = create_hotspot()
                    if create_hotspot_success:
                        hotspot_created = True
                    else:
                        print("Failed to create hotspot.")
            # Detect switch from on to off (button pressed)
            elif current_button_state == 1 and last_button_state == 0:
                print("Button pressed.")
                hotspot_created = False  # Reset the state to allow hotspot creation again
                charger_details = load_charger_details()
                close_hotspot_and_reconnect(interface='wlan0', original_ssid=charger_details['wifi_ssid'], original_password=charger_details['wifi_password'])
                
            last_button_state = current_button_state
            time.sleep(0.1)  # Polling interval was changed to 100ms for more responsive interaction


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

# Additional functions for handling Wi-Fi connections and hotspot creation
def disconnect_wifi_interface(interface='wlan0'):
    """Disconnects the specified Wi-Fi interface from any network."""
    try:
        subprocess.run(['nmcli', 'device', 'disconnect', interface], check=True)
        print(f"Disconnected {interface} from any connected networks.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to disconnect {interface}: {e}")


def create_hotspot(interface='wlan0'):
    """Create a WiFi hotspot with a fixed IP address."""
    hardware_details = load_or_generate_hardware_details()
    ssid = hardware_details['hardware_id']
    password = hardware_details.get('password', ''.join(random.choices(string.ascii_letters + string.digits, k=12)))

    # Define fixed IP address and subnet
    ip_address = "10.42.0.1/24"

    try:
        # Delete existing hotspot connection if exists
        subprocess.check_call(['nmcli', 'connection', 'delete', ssid], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        pass  # Ignore if the hotspot connection does not exist

    # Create a new hotspot connection with a static IP address
    try:
        try:
            disconnect_wifi_interface()
            # Turn off the Wi-Fi device
            subprocess.run(['nmcli', 'radio', 'wifi', 'off'], check=True)
            # Set the Wi-Fi device to managed mode
            subprocess.run(['nmcli', 'device', 'set', 'wlan0', 'managed', 'yes'], check=True)
            # Turn on the Wi-Fi device
            subprocess.run(['nmcli', 'radio', 'wifi', 'on'], check=True)
            # Create the Wi-Fi Hotspot
            subprocess.run(['nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', ssid, 'password', password], check=True)
            print(f"Hotspot '{ssid}' created successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to create hotspot: {e}")
        print("Hotspot created with SSID:", ssid)
        return True
    except subprocess.CalledProcessError as e:
        print("Failed to create hotspot:", e)
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
    # Initialize an empty message and assume form is valid initially
    message = ""
    form_is_valid = True

    if request.method == 'POST':
        # Retrieve form data
        ssid = request.form.get('wifi_ssid', '').strip()
        password = request.form.get('wifi_password', '').strip()
        server_url = request.form.get('server_url', '').strip()
        charger_id = request.form.get('charger_id', '').strip()

        # Basic validation checks
        if not ssid or not password or not server_url or not charger_id:
            message = "All fields are required."
            form_is_valid = False
        elif len(ssid) > 32:
            message = "SSID must be 32 characters or less."
            form_is_valid = False
        elif len(password) < 8:
            message = "Password must be at least 8 characters."
            form_is_valid = False

        if form_is_valid:
            # Attempt to connect to the new Wi-Fi network
            connection_success = connect_to_wifi(ssid, password)
            if connection_success:
                # Save the updated charger details including the WiFi SSID and password
                save_charger_details(server_url, charger_id, ssid, password)
                message = "Configuration updated successfully and connected to new Wi-Fi."
            else:
                # If connection fails, don't update the WiFi details in charger.json
                charger_details = load_charger_details()
                save_charger_details(server_url, charger_id, charger_details['wifi_ssid'], charger_details['wifi_password'])
                message = "Failed to connect to new Wi-Fi. Charger details updated without changing Wi-Fi settings."

    # Load charger details and charging sessions for rendering the page
    charger_details = load_charger_details()
    all_charging_sessions = load_charging_sessions()
    latest_charging_sessions = all_charging_sessions[-10:]  # Get the last 10 sessions

    return render_template('index.html', message=message, 
                           charger_details=charger_details,
                           charging_sessions=latest_charging_sessions)  # Pass only latest sessions


if __name__ == '__main__':
    setup_emergency_stop_pin()
    if is_raspberry_pi() and pi:
        emergency_button_thread = threading.Thread(target=monitor_emergency_button)
        emergency_button_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
