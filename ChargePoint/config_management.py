import json
import asyncio
import logging

# Placeholder for actual configuration file path or system-specific configuration management
CONFIG_FILE = './config.json'

async def handle_get_configuration(charge_point, requested_keys=None):
    """
    Retrieves configuration settings for the charge point asynchronously.
    :param charge_point: The charge point instance.
    :param requested_keys: Optional list of keys to retrieve specific configurations.
    """
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            config_data = json.load(config_file)
        
        configuration = []
        # If no specific keys requested, fetch all configuration
        requested_keys = requested_keys or config_data.keys()

        for key in requested_keys:
            if key in config_data:
                configuration.append({
                    "key": key,
                    "value": str(config_data[key]),
                    "readonly": key in charge_point.read_only_parameters
                })
            else:
                logging.warning(f"Requested key {key} not found in configuration.")

        logging.info(f"Configuration retrieved: {configuration}")
        return configuration

    except json.JSONDecodeError:
        logging.error("Failed to decode JSON from the configuration file.")
        return []
    except FileNotFoundError:
        logging.error("Configuration file not found.")
        return []
    except Exception as e:
        logging.error(f"Unhandled error retrieving configuration: {e}")
        return []

async def handle_set_configuration(charge_point, key, value):
    """
    Sets or updates a configuration setting for the charge point asynchronously.
    :param charge_point: The charge point instance.
    :param key: Configuration key to set or update.
    :param value: New value for the configuration setting.
    """
    try:
        with open(CONFIG_FILE, 'r+') as config_file:
            config_data = json.load(config_file)

            if key in charge_point.read_only_parameters:
                logging.error(f"Attempt to set read-only parameter {key}.")
                return False

            # Check if the key exists in the configuration to update
            if key in config_data:
                # Type-specific validation or transformation before setting the value
                if isinstance(config_data[key], int):
                    config_data[key] = int(value)
                elif isinstance(config_data[key], list):
                    config_data[key] = value.split(',')
                else:
                    config_data[key] = value

                # Reset the file pointer to the beginning and update the file
                config_file.seek(0)
                json.dump(config_data, config_file, indent=4)
                config_file.truncate()
                logging.info(f"Configuration for {key} set to {value}.")
                return True
            else:
                logging.error(f"Key {key} does not exist in the configuration.")
                return False

    except ValueError as e:
        logging.error(f"Invalid type for {key}: {e}")
        return False
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON from the configuration file.")
        return False
    except FileNotFoundError:
        logging.error("Configuration file not found.")
        return False
    except Exception as e:
        logging.error(f"Unhandled error setting configuration: {e}")
        return False
