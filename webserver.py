from flask import Flask, request, render_template
import json
import subprocess


app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        wifi_ssid = request.form.get('wifi_ssid')
        wifi_password = request.form.get('wifi_password')
        server_url = request.form.get('server_url')
        charger_id = request.form.get('charger_id')
        hotspot_enable = request.form.get('hotspot_enable') == 'on'
        hotspot_name = request.form.get('hotspot_name')
        hotspot_password = request.form.get('hotspot_password')

        # Update the charger configuration
        charger_config = {
            'server_url': server_url,
            'charger_id': charger_id,
            'hotspot_enable': hotspot_enable,
            'hotspot_name': hotspot_name,
            'hotspot_password': hotspot_password
        }

        # Save the charger configuration to a JSON file
        with open('./charger.json', 'w') as f:
            json.dump(charger_config, f)

        # Update WiFi configuration
        wifi_status = ''
        if wifi_ssid and wifi_password:
            try:
                subprocess.run(['nmcli', 'device', 'wifi', 'connect', wifi_ssid, 'password', wifi_password], check=True)
                wifi_status = 'WiFi connected successfully!'
            except subprocess.CalledProcessError:
                wifi_status = 'Failed to connect to WiFi. Please check your credentials.'

        # Update hotspot configuration
        hotspot_status = ''
        if hotspot_enable:
            # Add commands to turn on the hotspot and configure it with the provided name and password
            # This is just a placeholder and needs to be replaced with actual commands for your system
            hotspot_status = 'Hotspot turned on successfully!'

        return f'{wifi_status} {hotspot_status} Configuration updated successfully!'
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
