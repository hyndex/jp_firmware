import asyncio
import csv
import json
import logging
import os
import platform
import re
import subprocess
import threading
from datetime import datetime
import time
from lcd_display_20_4 import update_lcd_line
from MFRC522 import SimpleMFRC522

import aioserial
import requests
import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (Action, AuthorizationStatus, ClearCacheStatus,
                            ConfigurationStatus, MessageTrigger, RegistrationStatus,
                            ResetStatus, ResetType, TriggerMessageStatus)

if platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model'):
    import pigpio



# Constants
CONFIG_FILE = "config.json"
CHARGER_CONFIG_FILE = "charger.json"
CSV_FILENAME = "charging_sessions.csv"
FIRMWARE_FILE = "firmware.py"
BACKUP_FIRMWARE_FILE = "firmware_backup.py"
TEMP_CSV_FILE = "temp.csv"
NEW_FIRMWARE_PREFIX = "new_firmware_"
SERIAL_PORT = '/dev/serial0'
BAUD_RATE = 9600
# GPIO Pins for Emergency Stop Condition
EMERGENCY_STOP_PIN1 = 5  # GPIO pin number
EMERGENCY_STOP_PIN2 = 6  # Another GPIO pin number


# Logging configuration
logging.basicConfig(level=logging.INFO)

# Functions
def load_json_config(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Failed to load JSON config from {file_path}: {e}")
        return {}

def is_raspberry_pi():
    if platform.system() == 'Linux':
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

def get_relay_pins():
    return {1: 22, 2: 27, 3: 10}

# Classes
class RelayController:
    def __init__(self, relay_pin):
        self.relay_pin = relay_pin
        self.relay_state = 0  # 0: Off, 1: On
        self.last_rfid_read = {"id": None, "text": ""}
        self.RFID_EXPIRY_TIME = 5  # Seconds to consider the RFID tag as new

        if is_raspberry_pi():
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise RuntimeError("pigpio daemon is not running")
            self.pi.set_mode(self.relay_pin, pigpio.OUTPUT)

    def open_relay(self):
        if is_raspberry_pi():
            self.pi.write(self.relay_pin, 1)
        else:
            self.relay_state = 1
        logging.info(f'Relay on GPIO {self.relay_pin} is turned ON.')

    def close_relay(self):
        if is_raspberry_pi():
            self.pi.write(self.relay_pin, 0)
        else:
            self.relay_state = 0
        logging.info(f'Relay on GPIO {self.relay_pin} is turned OFF.')

class ChargePoint(cp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if is_raspberry_pi():
            self.pi = pigpio.pi()
            self.setup_emergency_stop_pins()
            if not self.pi.connected:
                raise RuntimeError("pigpio daemon is not running")
            
        self.initialize_csv()
        self.last_rfid_data = {"id": None, "text": ""}
        self.RFID_EXPIRY_TIME = 5  # Seconds
        self.emergency_status=0
        self.last_sent_status_info = {}

        self.meter = {}
        self.config = load_json_config(CONFIG_FILE)
        self.active_transactions = self.config.get("active_transactions", {})
        relay_pins = self.config.get("RelayPins", {})
        self.relay_controllers = {int(connector_id): RelayController(relay_pin) for connector_id, relay_pin in relay_pins.items()}
        self.connector_status = {connector_id: {"status": "Available", "error_code": "NoError", "notification_sent": False}
                                 for connector_id in range(1, int(self.config.get("NumberOfConnectors", 2)) + 1)}
                                 
        self.function_call_queue = asyncio.Queue()
        asyncio.create_task(self.process_function_call_queue())
        for connector_id in range(len(self.connector_status)):
            self.relay_controllers[connector_id+1].close_relay()

        self.reset_data()


        


    async def update_specific_lcd_line(self, line_number, message):
        """
        Update a specific line on the LCD with the given message.
        :param line_number: The line number to update (1-4).
        :param message: The message to display on the line.
        """
        # Call the update_lcd_line function with the specific line and message
        update_lcd_line(line_number, message)


    async def monitor_and_process_rfid(self):
        """Monitors for RFID tags and processes them."""
        logging.info('RFID monitoring started.')

        if(is_raspberry_pi):
            reader = SimpleMFRC522(pi=self.pi) 
            last_write_time = time.time()

            while True:
                try:
                    id, text = reader.read_no_block()
                    if id:
                        text = text.strip("\x00") if text else ""
                        current_time = time.time()

                        # Log every RFID read for auditing and debugging
                        logging.debug(f"RFID read: ID {id}, Text: '{text}'.")

                        # Compare new read with last saved RFID data
                        if id != self.last_rfid_read["id"] or text != self.last_rfid_read["text"] or (current_time - last_write_time >= self.RFID_EXPIRY_TIME):
                            self.last_rfid_read = {"id": str(id), "text": text}
                            logging.info(f"New RFID data: ID {id}, Text: '{text}'.")

                            # Loop through all connectors and initiate transactions if the connector is available
                            for connector_id, status_info in self.connector_status.items():
                                if status_info['status'] == 'Available':
                                    logging.info(f"Initiating transaction for connector {connector_id} with RFID ID {id}.")
                                    await self.function_call_queue.put({
                                        "function": self.start_transaction,
                                        "args": [connector_id, str(id)],
                                        "kwargs": {}
                                    })

                        last_write_time = current_time
                    else:
                        # Log when no RFID is read, this can be set to DEBUG if logging every second is too verbose
                        logging.debug("No RFID tag read.")

                    await asyncio.sleep(4)  # Non-blocking wait before checking for RFID tag again
                except Exception as e:
                    logging.error(f"Error in RFID monitoring loop: {e}")

    async def emergency_stop_all_transactions(self):
        logging.info("Initiating emergency stop for all transactions.")
        for connector_id in list(self.active_transactions.keys()):
            # await self.stop_transaction(connector_id, reason='EmergencyStop')

            await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id, 'EmergencyStop'], "kwargs": {}})
            logging.debug(f"Transaction stopped for connector {connector_id}.")        
        logging.info("Emergency stop triggered for all transactions and connectors set to Unavailable.")

    def setup_emergency_stop_pins(self):
        # Set PIN1 as output, initially LOW
        self.pi.set_mode(EMERGENCY_STOP_PIN1, pigpio.OUTPUT)
        self.pi.write(EMERGENCY_STOP_PIN1, 0)  # Send LOW signal

        # Set PIN2 as input with pull-up (expecting to be pulled low by pressing the switch)
        self.pi.set_mode(EMERGENCY_STOP_PIN2, pigpio.INPUT)
        self.pi.set_pull_up_down(EMERGENCY_STOP_PIN2, pigpio.PUD_UP)
    

    async def monitor_emergency_stop_pins(self):
        logging.info('Asynchronously monitoring emergency stop pins.')
        if(is_raspberry_pi()):
            while True:
                # Asynchronously check the pin state
                if self.pi.read(EMERGENCY_STOP_PIN2) == 1 and self.emergency_status==0:
                    self.emergency_status=1
                    logging.info("Emergency stop switch CLOSED. Triggering emergency stop.")
                    for connector_id in self.connector_status.keys():
                        if self.emergency_status==0:
                            self.update_connector_status(connector_id=connector_id, status='Faulted', error_code='OtherError')
                        logging.debug(f"Connector status updated to Unavailable for connector {connector_id}.")
                    await self.emergency_stop_all_transactions()
                else:
                    self.emergency_status=0
                    logging.debug("Emergency stop switch OPEN.")
                await asyncio.sleep(0.1)  # Non-blocking delay


    def initialize_csv(self):
        try:
            with open(CSV_FILENAME, 'x', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Transaction ID', 'Meter Start', 'Current Meter Value', 'Meter Stop', 'Is Meter Stop Sent'])
        except FileExistsError:
            pass

    def add_transaction_to_csv(self, transaction_id, meter_start):
        with open(CSV_FILENAME, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([transaction_id, meter_start, '', '', 'No'])

    def update_transaction_in_csv(self, transaction_id, current_meter_value=None, meter_stop=None, is_meter_stop_sent=None):
        with open(CSV_FILENAME, 'r', newline='') as csvfile, open(TEMP_CSV_FILE, 'w', newline='') as tempfile:
            reader = csv.reader(csvfile)
            writer = csv.writer(tempfile)
            for row in reader:
                if row[0] == str(transaction_id):
                    if current_meter_value is not None:
                        row[2] = current_meter_value
                    if meter_stop is not None:
                        row[3] = meter_stop
                    if is_meter_stop_sent is not None:
                        row[4] = is_meter_stop_sent
                writer.writerow(row)
        os.replace(TEMP_CSV_FILE, CSV_FILENAME)

    def reset_data(self):
        # self.meter = {}
        self.config = load_json_config(CONFIG_FILE)
        self.active_transactions = self.config.get("active_transactions", {})
        # relay_pins = self.config.get("RelayPins", {})
        # self.relay_controllers = {int(connector_id): RelayController(relay_pin) for connector_id, relay_pin in relay_pins.items()}
        # self.connector_status = {connector_id: {"status": "Available", "error_code": "NoError", "notification_sent": False}
        #                          for connector_id in range(1, int(self.config.get("NumberOfConnectors", 2)) + 1)}
        self.function_call_queue = asyncio.Queue()
        asyncio.create_task(self.process_function_call_queue())
        # for connector_id in range(len(self.connector_status)):
        #     self.relay_controllers[connector_id+1].close_relay()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as file:
            json.dump(self.config, file)

    # def update_connector_status(self, connector_id, status=None, error_code=None):
    #     if status is not None:
    #         self.connector_status[connector_id]['status'] = status
    #     if error_code is not None:
    #         self.connector_status[connector_id]['error_code'] = error_code
    #     # Set notification_sent to False only if the status or error_code has changed
    #     if self.connector_status[connector_id].get('status') != self.last_sent_status_info.get(connector_id, {}).get('status') or \
    #        self.connector_status[connector_id].get('error_code') != self.last_sent_status_info.get(connector_id, {}).get('error_code'):
    #         self.connector_status[connector_id]['notification_sent'] = False
    #     asyncio.create_task(self.send_status_notification(connector_id))

    def update_connector_status(self, connector_id, status=None, error_code=None):
        status_changed = False
        if status is not None and self.connector_status[connector_id]['status'] != status:
            self.connector_status[connector_id]['status'] = status
            status_changed = True

        if error_code is not None and self.connector_status[connector_id]['error_code'] != error_code:
            self.connector_status[connector_id]['error_code'] = error_code
            status_changed = True

        # Only mark for notification if there's a change
        if status_changed:
            self.connector_status[connector_id]['notification_sent'] = False
            asyncio.create_task(self.send_status_notification(connector_id))
        else:
            logging.info(f"No change in status for connector {connector_id}, skipping notification.")

    # async def process_function_call_queue(self):
    #     while True:
    #         function_call = await self.function_call_queue.get()
    #         logging.info(f"Processing function call: {function_call['function'].__name__}")
    #         try:
    #             if asyncio.iscoroutinefunction(function_call["function"]):
    #                 asyncio.create_task(function_call["function"](*function_call["args"], **function_call["kwargs"]))
    #             else:
    #                 loop = asyncio.get_event_loop()
    #                 loop.run_in_executor(None, function_call["function"], *function_call["args"], **function_call["kwargs"])
    #         except Exception as e:
    #             logging.error(f"Error processing function call: {e}")
    #         finally:
    #             self.function_call_queue.task_done()

    async def process_function_call_queue(self):
        while True:
            function_call = await self.function_call_queue.get()
            logging.info(f"Processing function call: {function_call['function'].__name__}")
            try:
                if asyncio.iscoroutinefunction(function_call["function"]):
                    # Use create_task to ensure the coroutine is scheduled for execution
                    task = asyncio.create_task(function_call["function"](*function_call["args"], **function_call["kwargs"]))
                    await task  # Wait for the task to complete to handle exceptions properly
                else:
                    # For non-coroutine functions, run in executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, function_call["function"], *function_call["args"], **function_call["kwargs"])
            except Exception as e:
                logging.error(f"Error processing function call: {e}")
            finally:
                self.function_call_queue.task_done()


    async def send_boot_notification(self, retries=0):
        max_retries = int(self.config.get("MaxBootNotificationRetries", 5))
        retry_interval = int(self.config.get("BootNotificationRetryInterval", 10))
        if retries > max_retries:
            logging.error("Max boot notification retries reached. Giving up.")
            return
        request = call.BootNotificationPayload(charge_point_model=self.config.get('Model'), charge_point_vendor=self.config.get('Vendor'))
        logging.info(f"Sending BootNotification request: {request}")
        try:
            response = await self.call(request)
            logging.info(f"Boot notification response: {response}")
            if response.status == RegistrationStatus.accepted:
                self.connected = True
                logging.info("Connected to central system.")
                for connector_id in self.connector_status:
                    if connector_id in self.active_transactions:
                        self.update_connector_status(connector_id=connector_id, status='Charging', error_code='NoError')
                    else:
                        self.update_connector_status(connector_id=connector_id, status='Available', error_code='NoError')
            else:
                logging.warning("Boot notification not accepted. Retrying...")
                await asyncio.sleep(retry_interval)
                await self.send_boot_notification(retries + 1)
        except Exception as e:
            logging.error(f"Error sending boot notification: {e}. Retrying...")
            await asyncio.sleep(retry_interval)
            await self.send_boot_notification(retries + 1)

    async def heartbeat(self):
        heartbeat_interval = int(self.config.get('HeartbeatInterval', 30))
        while True:
            await asyncio.sleep(heartbeat_interval)
            request = call.HeartbeatPayload()
            response = await self.call(request)
            logging.info(f"Heartbeat sent/received at {datetime.now()}: {response}")

    async def authorize(self, id_tag):
        request = call.AuthorizePayload(id_tag=id_tag)
        response = await self.call(request)
        return response.id_tag_info['status'] == AuthorizationStatus.accepted

    async def send_status_notifications_loop(self):
        while True:
            for connector_id, status_info in self.connector_status.items():
                if not status_info['notification_sent']:
                    await self.send_status_notification(connector_id)
            await asyncio.sleep(1)

    async def send_status_notification(self, connector_id):
        status_info = self.connector_status[connector_id]
        # Proceed only if a notification hasn't been sent for the current status and error_code
        if not status_info['notification_sent']:
            request = call.StatusNotificationPayload(connector_id=connector_id, status=status_info['status'], error_code=status_info['error_code'])
            await self.call(request)
            if(status_info['status'] != 'Charging'):
                await self.update_specific_lcd_line(connector_id, f'{status_info["status"]} {status_info["error_code"]}')
            status_info['notification_sent'] = True
            # Update last sent status info to current for comparison in future updates
            self.last_sent_status_info[connector_id] = {'status': status_info['status'], 'error_code': status_info['error_code']}
            logging.info(f"StatusNotification sent for connector {connector_id} with status {status_info['status']} and error_code {status_info['error_code']}")
    
    async def start_transaction(self, connector_id, id_tag):
        if connector_id not in self.active_transactions:
            meter_start = self.get_meter_value(connector_id)
            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not started.")
                return False
            request = call.StartTransactionPayload(connector_id=connector_id, id_tag=id_tag, meter_start=int(meter_start['energy']), timestamp=datetime.utcnow().isoformat())
            response = await self.call(request)
            transaction_id = response.transaction_id
            transaction = {"transaction_id": transaction_id, "connector_id": connector_id, "id_tag": id_tag, "meter_start": int(meter_start['energy']), "start_time": datetime.now()}
            self.active_transactions[connector_id] = transaction
            self.relay_controllers[connector_id].open_relay()
            self.update_connector_status(connector_id=connector_id, status='Charging', error_code='NoError')
            self.add_transaction_to_csv(transaction_id, int(meter_start['energy']))
            logging.info(f"Transaction {transaction_id} started on connector {connector_id}")
            return True
        else:
            logging.error(f"Connector {connector_id} is already in use")
            return False

    async def stop_transaction(self, connector_id, reason='Remote'):
        if connector_id in self.active_transactions:
            transaction = self.active_transactions[connector_id]
            transaction_id = transaction['transaction_id']
            meter_stop = int(self.get_meter_value(connector_id)['energy'])
            id_tag = transaction['id_tag']
            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not stopped.")
                return False
            valid_reasons = ['EmergencyStop', 'EVDisconnected', 'HardReset', 'Local', 'Other', 'PowerLoss', 'Reboot', 'Remote', 'SoftReset', 'UnlockCommand', 'DeAuthorized']
            reason = reason if reason in valid_reasons else 'Other'
            stop_transaction_request = call.StopTransactionPayload(meter_stop=meter_stop, timestamp=datetime.now().isoformat(), transaction_id=transaction_id, reason=reason)
            self.update_transaction_in_csv(transaction_id, meter_stop=meter_stop, is_meter_stop_sent='Yes')
            await self.call(stop_transaction_request, suppress=True)
            self.relay_controllers[connector_id].close_relay()
            
            if reason not in ['EmergencyStop', 'PowerLoss']:
                self.update_connector_status(connector_id, status='Available', error_code='NoError')
            del self.active_transactions[connector_id]

    async def send_periodic_meter_values(self):
        while True:
            for connector_id, transaction in self.active_transactions.items():
                meter_value = self.get_meter_value(connector_id)
                sampled_data_config = self.config.get("MeterValuesSampledData", [])
                sampled_values = []
                for data in sampled_data_config:
                    if data == "Energy.Active.Import.Register":
                        sampled_values.append({"value": str(meter_value.get('energy', 0)), "context": "Sample.Periodic", "format": "Raw", "measurand": data, "location": "EV", "unit": "Wh"})
                    elif data == "Voltage":
                        voltage = meter_value.get('voltage', 0)
                        if voltage < int(self.config.get("VoltageRestrictions_min", 210)):
                            self.update_connector_status(connector_id, status='Faulted', error_code='UnderVoltage')
                            await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id], "kwargs": {"reason": "SuspendedEVSE"}})
                        elif voltage > int(self.config.get("VoltageRestrictions_max", 260)):
                            self.update_connector_status(connector_id, status='Faulted', error_code='OverVoltage')
                            await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id], "kwargs": {"reason": "SuspendedEVSE"}})
                        sampled_values.append({"value": str(voltage), "format": "Raw", "measurand": data, "unit": "V"})
                    elif data == "Current.Import":
                        current = meter_value.get('current', 0)
                        if current > int(self.config.get("CurrentRestrictions_max", 20)):
                            self.update_connector_status(connector_id, status='Faulted', error_code='OverCurrentFailure')
                            await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id], "kwargs": {"reason": "SuspendedEVSE"}})
                        sampled_values.append({"value": str(current), "format": "Raw", "measurand": data, "unit": "A"})
                    elif data == "Power.Active.Import":
                        if datetime.datetime.now() - transaction['start_time'] >= datetime.timedelta(minutes=int(self.config.get("PowerTimingRestrictions_duration_minutes", 1))):  # Check if a minute has passed since the session start
                            if meter_value.get('power', 0) < int(self.config.get("PowerTimingRestrictions_threshold", 100)):  # Check if the power is less than 100 watts
                                await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id], "kwargs": {"reason": "SuspendedEVSE"}})
                        sampled_values.append({"value": str(meter_value.get('power', 0)), "format": "Raw", "measurand": data, "unit": "W"})
                request = call.MeterValuesPayload(connector_id=connector_id, transaction_id=transaction['transaction_id'], meter_value=[{"timestamp": datetime.utcnow().isoformat(), "sampled_value": sampled_values}])
                await self.call(request)
                self.update_transaction_in_csv(transaction['transaction_id'], current_meter_value=meter_value['energy'])

                energy = meter_value.get('energy', 0)  # Assuming 'energy' key holds the energy value in Wh
                energy_display_message = f"Energy: {energy}Wh"
                await self.update_specific_lcd_line(connector_id, energy_display_message)

            await asyncio.sleep(int(self.config.get("MeterValueSampleInterval", 60)))


    @on(Action.TriggerMessage)
    async def on_trigger_message(self, **kwargs):
        requested_message = kwargs.get('requested_message')
        connector_id = kwargs.get('connector_id', None)
        status = TriggerMessageStatus.notImplemented
        if requested_message == MessageTrigger.boot_notification:
            await self.function_call_queue.put({"function": self.send_boot_notification, "args": [], "kwargs": {}})
            status = TriggerMessageStatus.accepted
        elif requested_message == MessageTrigger.heartbeat:
            await self.function_call_queue.put({"function": self.heartbeat, "args": [], "kwargs": {}})
            status = TriggerMessageStatus.accepted
        elif requested_message == MessageTrigger.status_notification:
            self.last_sent_status_info = {}
            connector_id = connector_id if connector_id is not None else 1
            await self.function_call_queue.put({"function": self.send_status_notification, "args": [connector_id], "kwargs": {}})
            status = TriggerMessageStatus.accepted
        return call_result.TriggerMessagePayload(status=status)

    @on(Action.UpdateFirmware)
    async def on_update_firmware(self, **kwargs):
        url = kwargs.get('location')
        firmware_file = f'{NEW_FIRMWARE_PREFIX}{str(datetime.now())}.py'
        if self.download_firmware(url, firmware_file):
            self.apply_firmware_update(firmware_file)
        else:
            logging.error('Firmware download failed.')

    @on(Action.ClearCache)
    async def on_clear_cache(self, **kwargs):
        self.reset_data()
        return call_result.ClearCachePayload(status=ClearCacheStatus.accepted)

    @on(Action.Reset)
    async def handle_reset(self, **kwargs):
        reset_type = kwargs.get('type')
        for connector_id in list(self.active_transactions.keys()):
            await self.stop_transaction(connector_id)
        for connector_id in self.connector_status:
            self.update_connector_status(connector_id=connector_id, status='Unavailable', error_code='NoError')
            asyncio.create_task(self.send_status_notification(connector_id))
        await asyncio.sleep(5)
        reset_response = call_result.ResetPayload(status=ResetStatus.accepted)
        def delayed_restart():
            time.sleep(5)
            if reset_type == ResetType.soft:
                logging.info("Performing soft reset using PM2...")
                subprocess.run(['pm2', 'restart', 'all'])
            elif reset_type == ResetType.hard:
                logging.info("Performing hard reset...")
                subprocess.run(['sudo', 'reboot'])
        threading.Thread(target=delayed_restart).start()
        return reset_response

    @on(Action.GetConfiguration)
    async def handle_get_configuration(self, **kwargs):
        requested_keys = kwargs.get('key', [])
        configuration = []
        readonly_parameters = set(self.config.get("ReadOnlyParameters", []))
        if not requested_keys:
            requested_keys = list(self.config.keys())
        for key in requested_keys:
            if key in self.config:
                value = self.config[key]
                if isinstance(value, list):
                    value = ",".join(map(str, value))
                else:
                    value = str(value)
                configuration.append({"key": key, "value": value, "readonly": key in readonly_parameters})
        return call_result.GetConfigurationPayload(configuration_key=configuration)

    @on(Action.ChangeConfiguration)
    async def handle_set_configuration(self, **kwargs):
        key = kwargs.get('key')
        value = kwargs.get('value')
        readonly_parameters = set(self.config.get("ReadOnlyParameters", []))
        if key in readonly_parameters:
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
        if key in self.config:
            if isinstance(self.config[key], int):
                try:
                    value = int(value)
                except ValueError:
                    return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
            elif isinstance(self.config[key], list):
                value = value.split(",")
            self.config[key] = value
            self.save_config()
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.accepted)
        else:
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.not_supported)

    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(self, **kwargs):
        id_tag = kwargs.get('id_tag')
        connector_id = kwargs.get('connector_id', 1)
        if connector_id in self.active_transactions:
            logging.info(f"Connector {connector_id} is already in use.")
            return call_result.RemoteStartTransactionPayload(status='Rejected')
        await self.function_call_queue.put({"function": self.start_transaction, "args": [connector_id, id_tag], "kwargs": {}})
        return call_result.RemoteStartTransactionPayload(status='Accepted')

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(self, **kwargs):
        transaction_id = kwargs.get('transaction_id')
        for connector_id, transaction in self.active_transactions.items():
            if transaction['transaction_id'] == transaction_id:
                await self.function_call_queue.put({"function": self.stop_transaction, "args": [connector_id, 'Remote'], "kwargs": {}})
                return call_result.RemoteStopTransactionPayload(status='Accepted')
        return call_result.RemoteStopTransactionPayload(status='Rejected')

    def get_meter_value(self, connector_id):
        return self.meter.get(connector_id, {'voltage': 0, 'current': 0, 'power': 0, 'energy': 0})

    def parse_metervalues(self, s):
        parts = re.split(r',(?=M)', s)
        result = {}
        for part in parts:
            values = part.split(',')
            key = int(values[0].replace('M', ''))
            voltage = float(values[1])
            current = float(values[2])
            power = float(values[3])
            if current < 0.3:
                current = 0
                power = 0
            result[key] = {'voltage': voltage, 'current': current, 'power': power, 'energy': 0}
        return result

    async def read_serial_data(self):
        if not is_raspberry_pi():
            logging.info('Simulating meter readings [Device is not recognised as PI]')
            sleep_interval = 10
            try:
                while True:
                    for key in range(1, int(self.config.get("NumberOfConnectors", 2)) + 1):
                        if key not in self.meter:
                            temp = {'voltage': 220, 'current': 60, 'power': 220 * 60, 'energy': 0}
                            self.meter[key] = temp
                        else:
                            self.meter[key]['energy'] += (self.meter[key]['power']) * (sleep_interval / 3600)
                    logging.info('Meter', self.meter)
                    await asyncio.sleep(sleep_interval)
            except asyncio.CancelledError:
                logging.info("Simulation cancelled.")
        else:
            try:
                ser = aioserial.AioSerial(port=SERIAL_PORT, baudrate=BAUD_RATE, parity=aioserial.PARITY_NONE, stopbits=aioserial.STOPBITS_ONE, bytesize=aioserial.EIGHTBITS, timeout=1)
                sleep_interval = 1
                try:
                    while True:
                        if ser.in_waiting > 0:
                            line = await ser.readline_async()
                            line = line.decode('utf-8').strip()
                            if line:
                                logging.info(line)
                                temp = self.parse_metervalues(line)
                                for key, values in temp.items():
                                    if key in self.meter:
                                        self.meter[key]['energy'] += (values['power']) * (sleep_interval / 3600)
                                    self.meter[key] = values
                        await asyncio.sleep(sleep_interval)
                except asyncio.CancelledError:
                    logging.info("Serial reading cancelled.")
                finally:
                    ser.close()
            except Exception as e:
                logging.error(f"Serial error: {e}")

    def download_firmware(self, url, destination):
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                with open(destination, 'wb') as file:
                    file.write(response.content)
                return True
        except Exception as e:
            logging.error(f'Error downloading firmware: {e}')
        return False

    def apply_firmware_update(self, firmware_file):
        try:
            os.rename(FIRMWARE_FILE, BACKUP_FIRMWARE_FILE)
            os.rename(firmware_file, FIRMWARE_FILE)
            subprocess.run(['python3', FIRMWARE_FILE], check=True)
        except subprocess.CalledProcessError:
            os.rename(BACKUP_FIRMWARE_FILE, FIRMWARE_FILE)
            subprocess.run(['python3', FIRMWARE_FILE])

# # Main function
# async def main():
#     charger_config = load_json_config(CHARGER_CONFIG_FILE)
#     server_url = charger_config['server_url']
#     charger_id = charger_config['charger_id']
#     async with websockets.connect(f"{server_url}/{charger_id}", subprotocols=["ocpp1.6j"]) as ws:
#         cp_instance = ChargePoint(charger_id, ws)
#         await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat(), cp_instance.send_periodic_meter_values(), cp_instance.send_status_notifications_loop(), cp_instance.read_serial_data(), cp_instance.async_monitor_emergency_stop_pins())

# if __name__ == "__main__":
#     asyncio.run(main())


# async def main():
#     charger_config = load_json_config(CHARGER_CONFIG_FILE)
#     server_url = charger_config['server_url']
#     charger_id = charger_config['charger_id']

#     reconnection_delay = charger_config.get('reconnection_delay', 10)  # Reconnection delay in seconds

#     while True:
#         try:
#             # Try to connect to the server
#             async with websockets.connect(f"{server_url}/{charger_id}", subprotocols=["ocpp1.6j"]) as ws:
#                 cp_instance = ChargePoint(charger_id, ws)
#                 update_lcd_line(4, "Joulepoint, Online")
#                 await asyncio.gather(
#                     cp_instance.start(),
#                     cp_instance.send_boot_notification(),
#                     cp_instance.heartbeat(),
#                     cp_instance.send_periodic_meter_values(),
#                     cp_instance.send_status_notifications_loop(),
#                     cp_instance.read_serial_data(),
#                     cp_instance.async_monitor_emergency_stop_pins(),
#                     cp_instance.start_transaction_with_rfid()
#                 )
#         except (websockets.exceptions.WebSocketException, ConnectionRefusedError, ConnectionResetError) as e:
#             # Connection failed, log the error and wait before retrying
#             logging.error(f"Connection to server failed: {e}. Retrying in {reconnection_delay} seconds...")
#             update_lcd_line(4, "Server Disconnected. Retrying...")
#             await asyncio.sleep(reconnection_delay)
#         except KeyboardInterrupt:
#             # Program interrupted by user, break the loop and exit
#             break

# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         # Handle any cleanup here if necessary
#         logging.info("Application stopped by the user.")



async def main():
    charger_config = load_json_config(CHARGER_CONFIG_FILE)
    server_url = charger_config['server_url']
    charger_id = charger_config['charger_id']

    reconnection_delay = charger_config.get('reconnection_delay', 10)  # In seconds

    while True:
        try:
            # Attempt to connect to the server using websockets
            async with websockets.connect(f"{server_url}/{charger_id}", subprotocols=["ocpp1.6j"]) as ws:
                cp_instance = ChargePoint(charger_id, ws)

                # Display a message on LCD
                update_lcd_line(4, "Joulepoint, Online")

                # Run all tasks concurrently
                await asyncio.gather(
                    cp_instance.start(),
                    cp_instance.send_boot_notification(),
                    cp_instance.heartbeat(),
                    cp_instance.send_periodic_meter_values(),
                    cp_instance.send_status_notifications_loop(),
                    cp_instance.read_serial_data(),
                    # cp_instance.monitor_and_process_rfid(),
                    cp_instance.monitor_emergency_stop_pins(),
                )

        except (websockets.exceptions.WebSocketException, ConnectionRefusedError, ConnectionResetError) as e:
            # Handle reconnection on WebSocket errors
            logging.error(f"Connection to server failed: {e}. Retrying in {reconnection_delay} seconds...")
            update_lcd_line(4, "Server Disconnected. Retrying...")
            await asyncio.sleep(reconnection_delay)
        except Exception as e:
            # Handle any other exceptions
            logging.error(f"Unexpected error: {e}")
            update_lcd_line(4, "Unexpected Error. Retrying...")
            await asyncio.sleep(reconnection_delay)
        except KeyboardInterrupt:
            # Exit the loop if the program is interrupted by the user
            break

if __name__ == "__main__":
    # Run the main function until interrupted
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Cleanup and close operations
        logging.info("Application stopped by the user.")
