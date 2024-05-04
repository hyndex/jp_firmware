import os
import csv
import json
import requests
import logging
import subprocess

# Placeholder for configuration files and paths
CONFIG_FILE = '../settings/config.json'
CSV_FILENAME = '../settings/transactions.csv'

def load_json_config(file_path):
    """
    Loads the JSON configuration file.
    :param file_path: Path to the JSON config file.
    :return: Dictionary with configuration data.
    """
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {file_path}")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from the configuration file: {file_path}")
        return {}

def save_json_config(config, file_path):
    """
    Saves the specified configuration dictionary to a JSON file.
    :param config: Configuration dictionary to save.
    :param file_path: Path to the JSON config file.
    """
    try:
        with open(file_path, 'w') as file:
            json.dump(config, file, indent=4)
        logging.info("Configuration saved successfully.")
    except Exception as e:
        logging.error(f"Error saving configuration: {e}")

def download_firmware(url, destination):
    """
    Downloads firmware from a specified URL to a local file.
    :param url: URL from where to download the firmware.
    :param destination: Local path to save the downloaded file.
    :return: True if download was successful, False otherwise.
    """
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            with open(destination, 'wb') as file:
                file.write(response.content)
            return True
        else:
            logging.error(f"Failed to download firmware: HTTP {response.status_code}")
            return False
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return False

def apply_firmware_update(firmware_file):
    """
    Applies a firmware update by running a local script.
    :param firmware_file: Path to the firmware script file.
    :return: True if the update process was initiated successfully, False otherwise.
    """
    try:
        result = subprocess.run(['python3', firmware_file], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Firmware update failed: {e}")
        return False

def initialize_csv(file_path, headers):
    """
    Initializes a CSV file with specified headers if it does not already exist.
    :param file_path: Path to the CSV file.
    :param headers: List of header names for the CSV file.
    """
    if not os.path.exists(file_path):
        with open(file_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

def update_csv_transaction(file_path, transaction_id, **kwargs):
    """
    Updates a specific transaction in a CSV file.
    :param file_path: Path to the CSV file.
    :param transaction_id: ID of the transaction to update.
    :param kwargs: Key-value pairs of columns and their new values.
    """
    try:
        temp_file_path = file_path + '.tmp'
        with open(file_path, 'r', newline='') as csvfile, open(temp_file_path, 'w', newline='') as tempfile:
            reader = csv.reader(csvfile)
            writer = csv.writer(tempfile)
            headers = next(reader)
            writer.writerow(headers)
            for row in reader:
                if row[0] == str(transaction_id):
                    for key, value in kwargs.items():
                        index = headers.index(key)
                        row[index] = value
                writer.writerow(row)
        os.replace(temp_file_path, file_path)
    except Exception as e:
        logging.error(f"Failed to update transaction in CSV: {e}")



