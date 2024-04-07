import json
import subprocess

# Path to the hardware details JSON file
hardware_details_path = './hardware_details.json'

def read_hardware_details(filepath):
    """Reads hardware details from a JSON file."""
    try:
        with open(filepath, 'r') as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        print("Error: hardware_details.json not found.")
        return None
    except json.JSONDecodeError:
        print("Error: JSON decode error.")
        return None

# Additional functions for handling Wi-Fi connections and hotspot creation
def disconnect_wifi_interface(interface='wlan0'):
    """Disconnects the specified Wi-Fi interface from any network."""
    try:
        subprocess.run(['nmcli', 'device', 'disconnect', interface], check=True)
        print(f"Disconnected {interface} from any connected networks.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to disconnect {interface}: {e}")

def create_hotspot(ssid, password):
    """Creates a Wi-Fi hotspot using the specified SSID and password."""
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

def main():
    hardware_details = read_hardware_details(hardware_details_path)
    if hardware_details:
        ssid = hardware_details.get('hardware_id')
        password = hardware_details.get('password')
        if ssid and password:
            create_hotspot(ssid, password)
        else:
            print("Error: SSID or password missing in hardware_details.json.")
    else:
        print("Error: Unable to read hardware details.")

if __name__ == '__main__':
    main()
