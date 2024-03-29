import subprocess

def setup_hotspot(ssid, password):
    # Update the hostapd configuration
    hostapd_config = f"""interface=wlan0
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP"""

    with open('/etc/hostapd/hostapd.conf', 'w') as f:
        f.write(hostapd_config)

    # Update the dnsmasq configuration
    dnsmasq_config = """interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h"""

    with open('/etc/dnsmasq.conf', 'w') as f:
        f.write(dnsmasq_config)

    # Update the network interfaces configuration
    interfaces_config = """auto wlan0
iface wlan0 inet static
    address 192.168.4.1
    netmask 255.255.255.0
    network 192.168.4.0
    broadcast 192.168.4.255"""

    with open('/etc/network/interfaces.d/wlan0', 'w') as f:
        f.write(interfaces_config)

    # Enable IP forwarding
    subprocess.run(['sudo', 'sysctl', '-w', 'net.ipv4.ip_forward=1'], check=True)

    # Set up NAT
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', 'eth0', '-j', 'MASQUERADE'], check=True)
    subprocess.run(['sudo', 'sh', '-c', '"iptables-save > /etc/iptables.ipv4.nat"'], shell=True)

    # Update the rc.local file to apply NAT settings on boot
    with open('/etc/rc.local', 'a') as f:
        f.write('\niptables-restore < /etc/iptables.ipv4.nat\n')

    # Start the hostapd and dnsmasq services
    subprocess.run(['sudo', 'systemctl', 'unmask', 'hostapd'], check=True)
    subprocess.run(['sudo', 'systemctl', 'enable', 'hostapd'], check=True)
    subprocess.run(['sudo', 'systemctl', 'start', 'hostapd'], check=True)
    subprocess.run(['sudo', 'systemctl', 'start', 'dnsmasq'], check=True)

if __name__ == '__main__':
    ssid = 'PIZERO'
    password = 'sexyanupamsaikia'
    setup_hotspot(ssid, password)
