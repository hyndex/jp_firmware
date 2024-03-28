# JP Firmware Project

This project is designed to run on a Raspberry Pi and interfaces with an OCPP server for electric vehicle charging management. It uses Python and the `ocpp` library to handle OCPP messages and control relays based on charging commands.

## Prerequisites

- A Raspberry Pi with Raspberry Pi OS installed
- Internet connectivity for the Raspberry Pi
- Access to an OCPP server

## Setup Instructions

### 1. Clone the Repository

First, clone the repository to your Raspberry Pi:

```bash
git clone git@github.com:hyndex/jp_firmware.git
cd jp_firmware
```

### 2. Set Up a Virtual Environment

Create a Python virtual environment and activate it:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

### 4. Install PM2 (Optional)

PM2 is a process manager that can be used to manage and keep the application running in the background. To install PM2, you first need to install Node.js and npm:

```bash
curl -sL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Then, install PM2 globally using npm:

```bash
sudo npm install -g pm2
```

### 5. Start the Application

You can start the application directly using Python:

```bash
python main.py
```

Or, if you installed PM2, you can use it to start the application:

```bash
pm2 start ./venv/bin/python --name "jp_firmware" -- main.py
```

If you want the application to start automatically on boot, you can use PM2's startup feature:

```bash
pm2 startup
pm2 save
```

### 6. Configuration

The application uses a `config.json` file for configuration. You can edit this file to change settings such as the OCPP server URL, number of connectors, and more.

## Usage

Once the application is running, it will connect to the specified OCPP server and handle charging commands. You can monitor the application logs to see the interactions with the OCPP server.

## Stopping the Application

To stop the application, you can use:

```bash
python main.py stop
```

Or, if using PM2:

```bash
pm2 stop jp_firmware
```

---

Note: This README assumes that the user has basic knowledge of using a terminal and executing commands on a Raspberry Pi. Adjustments might be needed based on the specific setup and requirements of the user's environment.