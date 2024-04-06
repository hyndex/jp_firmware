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






to be done:


### General Observations

1. **Exception Handling**: It's good practice to implement comprehensive exception handling, especially for network requests and file operations, to avoid unexpected crashes.

2. **Configuration Management**: Using a JSON file for configuration is a good approach. Ensure sensitive information is securely stored and not hardcoded in your script or configuration files.

3. **Logging**: The use of the `logging` module is a good practice. Consider using different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) appropriately to provide more granular control over logging output.

4. **Code Structure**: Your script combines configuration loading, main application logic, and utility functions in a single file. Consider separating these concerns into different modules for better maintainability.

### Specific Suggestions and Fixes

1. **Relay Pin Configuration**:
   - You've hardcoded the relay pin configuration in the `get_relay_pins` function. Instead, this information is now retrieved from the `config.json`. Ensure your configuration file always contains the `RelayPins` section to prevent runtime errors.

2. **Emergency Stop Handling**:
   - Your emergency stop function directly calls `asyncio.run()`, which is not recommended inside async functions. Consider using `asyncio.create_task()` or scheduling the stop function on the event loop to avoid potential issues.

3. **CSV File Handling**:
   - When updating CSV files, you're reading and writing files in a way that could be optimized. Consider whether this could be streamlined or if a database might be more appropriate for your use case, especially with a large number of transactions.

4. **Error Handling in `send_boot_notification` and Other Network Calls**:
   - Network operations can fail for various reasons. Your retry logic in `send_boot_notification` and other places is a good start, but consider implementing exponential backoff to handle prolonged outages more gracefully.

5. **Use of `subprocess` and External Commands**:
   - You're using `subprocess.run()` to handle firmware updates and system resets. Ensure that any external command execution is securely handled to avoid injection attacks or unintended execution of harmful commands.

6. **Synchronous Blocking in Async Code**:
   - Be cautious with operations that can block the event loop, such as file operations and synchronous network requests (`requests.get`). For file I/O in async functions, consider using `aiofiles`. For HTTP requests, `aiohttp` could replace `requests` to maintain non-blocking behavior.

7. **Global Variable Usage**:
   - The script uses global variables for configuration paths and other constants. This is generally fine but be mindful of the potential for unexpected behavior if these values change or if your script grows in complexity.

8. **Compatibility and Error Handling with External Libraries**:
   - You're using `aioserial`, `websockets`, and potentially `pigpio` libraries. Ensure that you handle any library-specific exceptions and errors that could occur, particularly during long-running operations or when interacting with hardware.

9. **Firmware Update Procedure**:
   - Your firmware update process involves renaming files and executing potentially new and untested code. This is risky and could leave the system in an unstable state if not handled carefully. Ensure you have a rollback mechanism or a way to recover in case the new firmware is faulty.

10. **Concurrency and Resource Management**:
    - The script uses asyncio for concurrency. Ensure that resources (e.g., file handles, network connections) are properly managed and closed even in case of errors to prevent resource leaks.

### Testing and Validation

Before moving to production, thoroughly test your application under various conditions, including network failures, incorrect configurations, and hardware issues. Automated tests can help catch issues early, and a staging environment that mirrors production can help ensure stability.

Consider implementing monitoring and alerting to quickly detect and respond to issues once in production.

Lastly, ensure you comply with all relevant security practices, especially when dealing with network communications and executing system commands.


chmod +x setup.sh
