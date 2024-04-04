from flask import Flask, request, render_template, send_file
import json
import subprocess
import os

app = Flask(__name__)

def check_internet_connection():
    try:
        subprocess.check_output(['ping', '-c', '1', '8.8.8.8'])
        return True
    except subprocess.CalledProcessError:
        return False

def check_pm2_status():
    try:
        subprocess.check_output(['pm2', 'ping'])
        return True
    except subprocess.CalledProcessError:
        return False

def create_hotspot():
    ssid = 'MyHotspot'
    password = 'mypassword'
    try:
        subprocess.check_output(['nmcli', 'device', 'wifi', 'hotspot', 'con-name', ssid, 'ssid', ssid, 'band', 'bg', 'password', password])
        return True
    except subprocess.CalledProcessError:
        return False

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
    return render_template('index.html')

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

if __name__ == '__main__':
    # if not check_internet_connection() or not check_pm2_status():
    #     create_hotspot()
    app.run(host='0.0.0.0', port=5000, debug=True)
