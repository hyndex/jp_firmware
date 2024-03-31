#!/bin/bash

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
git clone git@github.com:hyndex/jp_firmware.git
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
pm2 start ./venv/bin/python --name "main" -- main.py

# Set up PM2 to start at boot
echo "Setting up PM2 to start at boot..."
pm2_startup_command=$(pm2 startup | grep 'sudo' | sed 's/\\//g')
eval $pm2_startup_command

# Save the PM2 process list
echo "Saving the PM2 process list..."
pm2 save

echo "Setup completed successfully!"
