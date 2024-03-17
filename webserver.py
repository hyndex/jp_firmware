from flask import Flask, request, render_template
import json
import subprocess
import os

app = Flask(__name__)

def update_hostapd_config(ssid, password):
    config_lines = [
        "interface=wlan0",
        f"ssid={ssid}",
        "hw_mode=g",
        "channel=7",
        "wmm_enabled=0",
        "macaddr_acl=0",
        "auth_algs=1",
        "ignore_broadcast_ssid=0",
        "wpa=2",
        f"wpa_passphrase={password}",
        "wpa_key_mgmt=WPA-PSK",
        "wpa_pairwise=TKIP",
        "rsn_pairwise=CCMP"
    ]
    with open('/etc/hostapd/hostapd.conf', 'w') as f:
        f.write('\n'.join(config_lines))

def update_dnsmasq_config():
    config_lines = [
        "interface=wlan0",
        "dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h"
    ]
    with open('/etc/dnsmasq.conf', 'w') as f:
        f.write('\n'.join(config_lines))

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

        charger_config = {
            'server_url': server_url,
            'charger_id': charger_id,
            'hotspot_enable': hotspot_enable,
            'hotspot_name': hotspot_name,
            'hotspot_password': hotspot_password
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

        hotspot_status = ''
        if hotspot_enable:
            try:
                update_hostapd_config(hotspot_name, hotspot_password)
                update_dnsmasq_config()
                subprocess.run(['sudo', 'systemctl', 'restart', 'hostapd'], check=True)
                subprocess.run(['sudo', 'systemctl', 'restart', 'dnsmasq'], check=True)
                hotspot_status = 'Hotspot started successfully!'
            except subprocess.CalledProcessError:
                hotspot_status = 'Failed to start hotspot. Please check your settings.'

        return f'{wifi_status} {hotspot_status} Configuration updated successfully!'
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
