import asyncio
import logging
import json
import requests
import re
import aioserial
from ocpp.v16.enums import Action
import os
import subprocess
import threading
import time
import csv
from datetime import datetime
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (RegistrationStatus, AuthorizationStatus,
                            ConfigurationStatus, ResetType, ResetStatus,
                            ClearCacheStatus, TriggerMessageStatus, MessageTrigger)
import pigpio
import sys
import os
logging.basicConfig(level=logging.INFO)

def load_charger_config():
    with open('charger.json', 'r') as file:
        return json.load(file)

# Function to get relay pins mapping
# def get_relay_pins():
#     return {1: 25, 2: 24, 3: 23}
    
# def get_relay_pins():
#     return {1: 6, 2: 24, 3: 23}


# pzam
    
def get_relay_pins():
    return {1: 22, 2: 27, 3: 10}


import platform

def is_raspberry_pi():
    if platform.system() == 'Linux':
        # Check if '/proc/device-tree/model' contains 'Raspberry Pi'
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

# Set IS_PI to 1 if running on a Raspberry Pi, otherwise 0
IS_PI = 1 if is_raspberry_pi() else 0

# Class to control a relay
# Class to control a relay using pigpio
class RelayController:
    def __init__(self, relay_pin):
        self.relay_pin = relay_pin
        if(IS_PI):
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise RuntimeError("pigpio daemon is not running")
            self.pi.set_mode(self.relay_pin, pigpio.OUTPUT)

    def open_relay(self):
        if(IS_PI):
            self.pi.write(self.relay_pin, 1)
        print(f'Relay on GPIO {self.relay_pin} is turned ON.')

    def close_relay(self):
        if(IS_PI):
            self.pi.write(self.relay_pin, 0)
        print(f'Relay on GPIO {self.relay_pin} is turned OFF.')


# ChargePoint class that extends the OCPP ChargePoint class
class ChargePoint(cp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_data()
        self.csv_filename = 'charging_sessions.csv'
        self.initialize_csv()


    def initialize_csv(self):
        try:
            with open(self.csv_filename, 'x', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Transaction ID', 'Meter Start', 'Current Meter Value', 'Meter Stop', 'Is Meter Stop Sent'])
        except FileExistsError:
            pass

    def add_transaction_to_csv(self, transaction_id, meter_start):
        with open(self.csv_filename, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([transaction_id, meter_start, '', '', 'No'])

    def update_transaction_in_csv(self, transaction_id, current_meter_value=None, meter_stop=None, is_meter_stop_sent=None):
        temp_filename = 'temp.csv'
        with open(self.csv_filename, 'r', newline='') as csvfile, open(temp_filename, 'w', newline='') as tempfile:
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
        os.replace(temp_filename, self.csv_filename)



    def update_connector_status(self, connector_id, status=None, error_code=None):
        if status is not None:
            self.connector_status[connector_id]['status'] = status
        if error_code is not None:
            self.connector_status[connector_id]['error_code'] = error_code
        self.connector_status[connector_id]['notification_sent'] = False
        # Trigger a status notification to inform the central system of the change
        asyncio.create_task(self.send_status_notification(connector_id))


    def reset_data(self):
        self.meter = {}
        self.config_file = "config.json"
        self.load_config()
        self.relay_controllers = {connector_id: RelayController(relay_pin) for connector_id, relay_pin in get_relay_pins().items()}
        self.active_transactions = {}
        self.connector_status = {connector_id: {"status": "Available", "error_code": "NoError", "notification_sent": False}
                                 for connector_id in range(1, int(self.config.get("NumberOfConnectors", 2)) + 1)}
        self.function_call_queue = asyncio.Queue()
        asyncio.create_task(self.process_function_call_queue())

        for connector_id in range(len(self.connector_status)):
            self.relay_controllers[connector_id+1].close_relay()


    def load_config(self):
        try:
            with open(self.config_file, 'r') as file:
                data = json.load(file)
                self.config = data
                self.active_transactions = data.get("active_transactions", {})
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Failed to load config: {e}")
            self.config = {"NumberOfConnectors": 2}

    def save_config(self):
        with open(self.config_file, 'w') as file:
            json.dump(self.config, file)

    async def process_function_call_queue(self):
        while True:
            function_call = await self.function_call_queue.get()
            logging.info(f"Processing function call: {function_call['function'].__name__}")
            try:
                if asyncio.iscoroutinefunction(function_call["function"]):
                    asyncio.create_task(function_call["function"](*function_call["args"], **function_call["kwargs"]))
                else:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, function_call["function"], *function_call["args"], **function_call["kwargs"])
            except Exception as e:
                logging.error(f"Error processing function call: {e}")
            finally:
                self.function_call_queue.task_done()

    # Charger Originating commands
    async def send_boot_notification(self, retries=0):
        if retries > int(self.config.get("MaxBootNotificationRetries", 5)):
            logging.error("Max boot notification retries reached. Giving up.")
            return

        request = call.BootNotificationPayload(
            charge_point_model=self.config.get('Model'),
            charge_point_vendor=self.config.get('Vendor'),
        )
        logging.info(f"Sending BootNotification request: {request}")
        try:
            response = await self.call(request)
            logging.info(f"Boot notification response: {response}")
            if response.status == RegistrationStatus.accepted:
                self.connected = True
                logging.info("Connected to central system.")
                # for connector_id in range(1, int(self.config.get("NumberOfConnectors", 3)) + 1):
                #     await self.function_call_queue.put({
                #         "function": self.send_status_notification,
                #         "args": [connector_id],
                #         "kwargs": {}
                #     })
            else:
                logging.warning("Boot notification not accepted. Retrying...")
                await asyncio.sleep(int(self.config.get("BootNotificationRetryInterval", 10)))
                await self.send_boot_notification(retries + 1)
        except Exception as e:
            logging.error(f"Error sending boot notification: {e}. Retrying...")
            await asyncio.sleep(int(self.config.get("BootNotificationRetryInterval", 10)))
            await self.send_boot_notification(retries + 1)

    async def heartbeat(self):
        while True:
            await asyncio.sleep(int(self.config.get('HeartbeatInterval'), 30)) 
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
            await asyncio.sleep(1)  # Adjust the interval as needed

    async def send_status_notification(self, connector_id):
        status_info = self.connector_status[connector_id]
        request = call.StatusNotificationPayload(
            connector_id=connector_id,
            status=status_info['status'],
            error_code=status_info['error_code']
        )
        await self.call(request)
        status_info['notification_sent'] = True
        logging.info(f"StatusNotification sent for connector {connector_id} with status {status_info['status']} and error code {status_info['error_code']}")

    async def start_transaction(self, connector_id, id_tag):
        if connector_id not in self.active_transactions:
            meter_start = self.get_meter_value(connector_id)
            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not started.")
                return False

            request = call.StartTransactionPayload(
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=int(meter_start['energy']),
                timestamp=datetime.utcnow().isoformat()
            )
            response = await self.call(request)
            transaction_id = response.transaction_id
            transaction = {
                "transaction_id": transaction_id,
                "connector_id": connector_id,
                "id_tag": id_tag,
                "meter_start": int(meter_start['energy']),
            }
            self.active_transactions[connector_id] = transaction
            self.relay_controllers[connector_id].open_relay()

            self.update_connector_status(connector_id=connector_id, status='Charging', error_code='NoError')
            self.add_transaction_to_csv(transaction_id, int(meter_start['energy']))
            logging.info(f"Transaction {transaction_id} started on connector {connector_id}")
            return True
        else:
            logging.error(f"Connector {connector_id} is already in use")
            return False
            
    async def stop_transaction(self, connector_id, reason=None):
        if connector_id in self.active_transactions:
            transaction = self.active_transactions[connector_id]
            transaction_id = transaction['transaction_id']
            meter_stop = int(self.get_meter_value(connector_id)['energy'])

            id_tag = transaction['id_tag']
            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not stopped.")
                return False

            # Validate the reason and set a default value if necessary
            valid_reasons = [
                'EmergencyStop', 'EVDisconnected', 'HardReset', 'Local',
                'Other', 'PowerLoss', 'Reboot', 'Remote', 'SoftReset',
                'UnlockCommand', 'DeAuthorized'
            ]
            if reason not in valid_reasons:
                reason = 'Other'  # Set a default value for an invalid or unspecified reason

            stop_transaction_request = call.StopTransactionPayload(
                meter_stop=meter_stop,
                timestamp=datetime.now().isoformat(),
                transaction_id=transaction_id,
                reason=reason
            )
            await self.call(stop_transaction_request, suppress=True)
            self.relay_controllers[connector_id].close_relay()
            self.update_transaction_in_csv(transaction_id, meter_stop=meter_stop, is_meter_stop_sent='Yes')


            # Update the connector status based on the reason
            if reason not in ['OverCurrent', 'VoltageOutOfRange']:
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
                        sampled_values.append({
                            "value": str(meter_value.get('energy', 0)),
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": data,
                            "location": "EV",
                            "unit": "Wh"
                        })
                    elif data == "Voltage":
                        sampled_values.append({
                            "value": str(meter_value.get('voltage', 0)),
                            "format": "Raw",
                            "measurand": data,
                            "unit": "V"
                        })
                    elif data == "Current.Import":
                        sampled_values.append({
                            "value": str(meter_value.get('current', 0)),
                            "format": "Raw",
                            "measurand": data,
                            "unit": "A"
                        })
                    elif data == "Power.Active.Import":
                        sampled_values.append({
                            "value": str(meter_value.get('power', 0)),
                            "format": "Raw",
                            "measurand": data,
                            "unit": "W"
                        })

                request = call.MeterValuesPayload(
                    connector_id=connector_id,
                    transaction_id=transaction['transaction_id'],
                    meter_value=[{
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": sampled_values
                    }]
                )
                await self.call(request)
                self.update_transaction_in_csv(transaction['transaction_id'], current_meter_value=meter_value['energy'])
            await asyncio.sleep(int(self.config.get("MeterValueSampleInterval", 60)))
        

    # Server Originating commands
    @on(Action.TriggerMessage)
    async def on_trigger_message(self, **kwargs):
        requested_message = kwargs.get('requested_message')
        connector_id = kwargs.get('connector_id', None)
        if requested_message == MessageTrigger.boot_notification:
            await self.function_call_queue.put({
                "function": self.send_boot_notification,
                "args": [],
                "kwargs": {}
            })
            status = TriggerMessageStatus.accepted
        elif requested_message == MessageTrigger.heartbeat:
            await self.function_call_queue.put({
                "function": self.heartbeat,
                "args": [],
                "kwargs": {}
            })
            status = TriggerMessageStatus.accepted
        elif requested_message == MessageTrigger.status_notification:
            connector_id = connector_id if connector_id is not None else 1
            await self.function_call_queue.put({
                "function": self.send_status_notification,
                "args": [connector_id],
                "kwargs": {}
            })
            status = TriggerMessageStatus.accepted
        else:
            status = TriggerMessageStatus.notImplemented
        return call_result.TriggerMessagePayload(status=status)

    @on(Action.UpdateFirmware)
    async def on_update_firmware(self, **kwargs):
        url = kwargs.get('location')
        firmware_file = f'new_firmware_{str(datetime.now())}.py'
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

        # Stop all active transactions
        for connector_id in list(self.active_transactions.keys()):
            await self.stop_transaction(connector_id)

        # Set the status of all connectors to "Unavailable" and send StatusNotification
        for connector_id in self.connector_status:
            self.update_connector_status(connector_id=connector_id, status='Unavailable', error_code='NoError')
            asyncio.create_task(self.send_status_notification(connector_id))

        # Wait for 5 seconds to allow some time for status notifications to be sent
        await asyncio.sleep(5)

        # Prepare the reset response
        reset_response = call_result.ResetPayload(status=ResetStatus.accepted)

        def delayed_restart():
            time.sleep(5)  # Delay the restart by 5 seconds
            if reset_type == ResetType.soft:
                logging.info("Performing soft reset using PM2...")
                subprocess.run(['pm2', 'restart', 'all'])
            elif reset_type == ResetType.hard:
                logging.info("Performing hard reset...")
                subprocess.run(['sudo', 'reboot'])

        # Start the delayed restart in a separate thread
        threading.Thread(target=delayed_restart).start()

        # Return the reset response
        return reset_response


    @on(Action.GetConfiguration)
    async def handle_get_configuration(self, **kwargs):
        requested_keys = kwargs.get('key', [])
        configuration = []
        readonly_parameters = set(self.config.get("ReadOnlyParameters", []))

        if not requested_keys:
            # If no specific keys are requested, return all configuration entries
            requested_keys = list(self.config.keys())

        for key in requested_keys:
            if key in self.config:
                value = self.config[key]
                if isinstance(value, list):
                    value = ",".join(map(str, value))  # Convert list to comma-separated string
                else:
                    value = str(value)  # Convert other types to string
                configuration.append({
                    "key": key,
                    "value": value,
                    "readonly": key in readonly_parameters
                })

        return call_result.GetConfigurationPayload(configuration_key=configuration)




    @on(Action.ChangeConfiguration)
    async def handle_set_configuration(self, **kwargs):
        key = kwargs.get('key')
        value = kwargs.get('value')
        readonly_parameters = set(self.config.get("ReadOnlyParameters", []))

        if key in readonly_parameters:
            # Reject the change if the parameter is read-only
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)

        if key in self.config:
            # Convert the value to the appropriate type before saving
            if isinstance(self.config[key], int):
                try:
                    value = int(value)
                except ValueError:
                    return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
            elif isinstance(self.config[key], list):
                value = value.split(",")
            # Update the configuration and save it
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
            print(f"Connector {connector_id} is already in use.")
            return call_result.RemoteStartTransactionPayload(status='Rejected')
        await self.function_call_queue.put({
            "function": self.start_transaction,
            "args": [connector_id, id_tag],
            "kwargs": {}
        })
        return call_result.RemoteStartTransactionPayload(status='Accepted')

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(self, **kwargs):
        transaction_id = kwargs.get('transaction_id')
        for connector_id, transaction in self.active_transactions.items():
            if transaction['transaction_id'] == transaction_id:
                await self.function_call_queue.put({
                    "function": self.stop_transaction,
                    "args": [connector_id],
                    "kwargs": {}
                })
                return call_result.RemoteStopTransactionPayload(status='Accepted')
        return call_result.RemoteStopTransactionPayload(status='Rejected')

    def get_meter_value(self, connector_id):
        return self.meter.get(connector_id, {'voltage': 0, 'current': 0, 'power': 0, 'energy': 0})

    def parse_metervalues(self, s):
        # Parse actual meter values from serial data
        parts = re.split(r',(?=M)', s)
        result = {}
        for part in parts:
            values = part.split(',')
            key = int(values[0].replace('M', ''))
            voltage = float(values[1])
            current = float(values[2])
            power = float(values[3])

            # Set current and power to 0 if current is less than 0.3
            if current < 0.3:
                current = 0
                power = 0

            result[key] = {
                'voltage': voltage,
                'current': current,
                'power': power,
                'energy': 0  # Initialize energy with 0
            }
        return result

    async def read_serial_data(self):
        if IS_PI == 0:
            print('Simulating meter readings [Device is not recognised as PI]')
            sleep_interval = 10  # Time interval between readings in seconds
            try:
                while True:
                    for key in range(1, int(self.config.get("NumberOfConnectors", 2)) + 1):
                        if key not in self.meter:
                            temp = {'voltage': 220, 'current': 60, 'power': 220*60, 'energy': 0}
                            self.meter[key] = temp
                        else:
                            # Increment energy by (power in kW) * (time interval in hours)
                            self.meter[key]['energy'] += (self.meter[key]['power']) * (sleep_interval / 3600)
                    print('Meter', self.meter)
                    await asyncio.sleep(sleep_interval)
            except asyncio.CancelledError:
                print("Simulation cancelled.")
        else:
            # Read actual meter data from serial when IS_PI is 1
            try:
                ser = aioserial.AioSerial(
                    port='/dev/serial0',
                    baudrate=9600,
                    parity=aioserial.PARITY_NONE,
                    stopbits=aioserial.STOPBITS_ONE,
                    bytesize=aioserial.EIGHTBITS,
                    timeout=1
                )
                sleep_interval = 1  # Time interval between readings in seconds
                try:
                    while True:
                        if ser.in_waiting > 0:
                            line = await ser.readline_async()
                            line = line.decode('utf-8').strip()
                            if line:
                                print(line)
                                temp = self.parse_metervalues(line)
                                for key, values in temp.items():
                                    if key in self.meter:
                                        self.meter[key]['energy'] += (values['power']) * (sleep_interval / 3600)
                                    self.meter[key] = values
                        await asyncio.sleep(sleep_interval)
                except asyncio.CancelledError:
                    print("Serial reading cancelled.")
                finally:
                    ser.close()
            except Exception as e:
                print(f"Serial error: {e}")

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
        backup_firmware = 'firmware_backup.py'
        current_firmware = 'firmware.py'
        try:
            os.rename(current_firmware, backup_firmware)
            os.rename(firmware_file, current_firmware)
            subprocess.run(['python3', current_firmware], check=True)
        except subprocess.CalledProcessError:
            os.rename(backup_firmware, current_firmware)
            subprocess.run(['python3', current_firmware])



# Main function to run the ChargePoint
async def main():
    charger_config = load_charger_config()
    server_url = charger_config['server_url']
    charger_id = charger_config['charger_id']
    async with websockets.connect(
            f"{server_url}/{charger_id}", subprotocols=["ocpp1.6j"]
    ) as ws:
        cp_instance = ChargePoint(charger_id, ws)
        await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat(),
                             cp_instance.send_periodic_meter_values(), cp_instance.send_status_notifications_loop(), cp_instance.read_serial_data())

if __name__ == "__main__":
    import websockets
    asyncio.run(main())
