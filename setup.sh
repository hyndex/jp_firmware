#!/bin/bash

# Update system packages
echo "Updating system packages..."
sudo apt-get update

# Install Node.js and npm
echo "Installing Node.js and npm..."
curl -sL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install pigpio
echo "Installing pigpio..."
sudo apt-get install -y pigpio python3-pigpio

# Start the pigpio daemon
echo "Starting the pigpio daemon..."
sudo systemctl start pigpiod
sudo systemctl enable pigpiod

# Install Git
echo "Installing Git..."
sudo apt-get install -y git

# Clone the repository
echo "Cloning the repository..."
git clone https://github.com/hyndex/jp_firmware.git
cd jp_firmware

# Set up a virtual environment
echo "Setting up a virtual environment..."
sudo apt-get install -y python3-venv
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install PM2
echo "Installing PM2..."
sudo npm install -g pm2

# Start the main.py script with PM2
echo "Starting the main.py script with PM2..."
# pm2 start ./venv/bin/python --name "main" -- main.py
# pm2 start ./venv/bin/python --name "webserver" -- webserver.py

# Set up PM2 to start at boot
echo "Setting up PM2 to start at boot..."
pm2_startup_command=$(pm2 startup | grep 'sudo' | sed 's/\\//g')
eval $pm2_startup_command

# Save the PM2 process list
echo "Saving the PM2 process list..."
pm2 save

# Enable serial interface
echo "Enabling serial interface..."
sudo sed -i 's/^#enable_uart=1/enable_uart=1/' /boot/config.txt
sudo sed -i '/console=serial0,115200/d' /boot/cmdline.txt

# Install and configure NetworkManager
echo "Installing NetworkManager..."
sudo apt-get install -y network-manager

echo "Stopping and disabling systemd-networkd and wpa_supplicant..."
sudo systemctl stop systemd-networkd wpa_supplicant
sudo systemctl disable systemd-networkd wpa_supplicant


echo "Enabling and starting NetworkManager..."
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager

# Connect to specified WiFi network
echo "Connecting to WiFi network 'Joulepoint-Charger-Wifi'..."
nmcli dev wifi connect 'Joulepoint-Charger-Wifi' password '1qaz2wsx'

# Enable SPI and I2C interfaces
echo "Enabling SPI and I2C interfaces..."
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Install i2c-tools (optional, for I2C device management and testing)
echo "Installing i2c-tools..."
sudo apt-get install -y i2c-tools

curl -fsSL https://tailscale.com/install.sh | sudo sh


# Install dnsmasq for DNS
echo "Installing dnsmasq for DNS management..."
sudo apt-get install -y dnsmasq

# Configure dnsmasq to resolve jp.local to the Raspberry Pi's IP address in the hotspot network
# echo "Configuring dnsmasq for jp.local resolution..."
# echo "address=/jp.local/10.42.0.1" | sudo tee -a /etc/dnsmasq.conf

# Restart dnsmasq to apply the changes
echo "Restarting dnsmasq to apply configurations..."
# sudo systemctl restart dnsmasq

echo "Setup completed successfully!"
