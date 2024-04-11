#!/bin/bash

# Function to safely execute a command and echo its action
safe_run() {
    echo "$2"
    if eval $1; then
        echo "Success: $2"
    else
        echo "Error executing: $1"
        exit 1
    fi
}

echo "Beginning setup..."

# System update and package installation
safe_run "sudo apt-get update" "Updating system packages..."
safe_run "curl -sL https://deb.nodesource.com/setup_20.x | sudo -E bash -" "Adding Node.js setup script..."
safe_run "sudo apt-get install -y nodejs" "Installing Node.js and npm..."
safe_run "sudo apt-get install -y pigpio python3-pigpio" "Installing pigpio..."
safe_run "sudo systemctl start pigpiod && sudo systemctl enable pigpiod" "Starting and enabling the pigpio daemon..."
safe_run "sudo apt-get install -y git" "Installing Git..."

# Clone the repository
safe_run "git clone https://github.com/hyndex/jp_firmware.git" "Cloning the repository..."

# Change directory to jp_firmware
cd jp_firmware || exit
echo "Changed directory to jp_firmware."

# Virtual environment setup and dependency installation
safe_run "sudo apt-get install -y python3-venv" "Installing Python venv..."
python3 -m venv venv
source venv/bin/activate
safe_run "pip install -r requirements.txt" "Installing Python dependencies from requirements.txt"

# PM2 setup and application start
safe_run "sudo npm install -g pm2" "Installing PM2..."
safe_run "pm2 start ./venv/bin/python --name 'webserver' -- webserver.py" "Starting the webserver with PM2..."

# Configure PM2 to start at boot
pm2_startup_command=$(pm2 startup | grep 'sudo' | sed 's/\\//g')
eval "$pm2_startup_command"
safe_run "pm2 save" "Saving the PM2 process list..."

# Hardware configurations
safe_run "sudo sed -i 's/^#enable_uart=1/enable_uart=1/' /boot/config.txt && sudo sed -i '/console=serial0,115200/d' /boot/cmdline.txt" "Enabling serial interface..."
safe_run "sudo raspi-config nonint do_spi 0 && sudo raspi-config nonint do_i2c 0" "Enabling SPI and I2C interfaces..."
safe_run "sudo apt-get install -y i2c-tools" "Installing i2c-tools..."

# Precaution before switching to NetworkManager
echo "NetworkManager will now be installed and configured. This may disrupt remote connections."
read -p "Press ENTER to continue or Ctrl+C to abort..."

# NetworkManager setup
safe_run "sudo apt-get install -y network-manager" "Installing NetworkManager..."
safe_run "sudo systemctl stop systemd-networkd wpa_supplicant && sudo systemctl disable systemd-networkd wpa_supplicant" "Disabling default network management services..."
safe_run "sudo systemctl enable NetworkManager && sudo systemctl start NetworkManager" "Enabling and starting NetworkManager..."

echo "Please manually reconnect to the device using the new network settings if the connection is lost."
read -p "Press ENTER to configure WiFi network after ensuring connectivity..."

# Now that NetworkManager is in charge, connect to the specified WiFi network
safe_run "nmcli dev wifi connect 'joulepoint' password 'joulepoint123'" "Connecting to WiFi network 'joulepoint'..."
