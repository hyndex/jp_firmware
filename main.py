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
    return {1: 27, 2: 22, 3: 10}


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
                for connector_id in range(1, int(self.config.get("NumberOfConnectors", 3)) + 1):
                    await self.function_call_queue.put({
                        "function": self.send_status_notification,
                        "args": [connector_id],
                        "kwargs": {}
                    })
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
            self.connector_status[connector_id]['status'] = 'Charging'
            self.connector_status[connector_id]['error_code'] = 'NoError'
            self.connector_status[connector_id]['notification_sent'] = False
            logging.info(f"Transaction {transaction_id} started on connector {connector_id}")
            return True
        else:
            logging.error(f"Connector {connector_id} is already in use")
            return False
            

    async def stop_transaction(self, connector_id):
        if connector_id in self.active_transactions:
            transaction = self.active_transactions[connector_id]
            transaction_id = transaction['transaction_id']
            id_tag = transaction['id_tag']
            meter_stop = int(self.get_meter_value(connector_id)['energy'])
            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not stopped.")
                return False

            try:
                stop_transaction_request = call.StopTransactionPayload(
                    meter_stop=int(meter_stop),
                    timestamp=datetime.utcnow().isoformat(),
                    transaction_id=transaction_id,
                    id_tag=id_tag,
                )
                await self.call(stop_transaction_request, suppress=True)
                self.relay_controllers[connector_id].close_relay()
                logging.info(f"Transaction {transaction_id} stopped on connector {connector_id}")
            except Exception as e:
                logging.error(f"Error occurred while stopping transaction: {e}")
            

            self.connector_status[connector_id]['status'] = 'Available'
            self.connector_status[connector_id]['error_code'] = 'NoError'
            self.connector_status[connector_id]['notification_sent'] = False
            del self.active_transactions[connector_id]
            await self.function_call_queue.put({
                "function": asyncio.sleep,
                "args": [20],
                "kwargs": {}
            })

            await self.function_call_queue.put({
                "function": self.call,
                "args": [
                    call.StatusNotificationPayload(
                        connector_id=connector_id,
                        status='Available',
                        error_code='NoError'
                    )
                ],
                "kwargs": {}
            })
            return True
        else:
            logging.warning(f"No active transaction found on connector {connector_id}")
            return False

    async def send_periodic_meter_values(self):
        while True:
            for connector_id, transaction in self.active_transactions.items():
                meter_value = self.get_meter_value(connector_id)
                energy_sampled_value = {
                    "value": str(meter_value['energy']),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "EV",
                    "unit": "Wh"
                }
                voltage_sampled_value = {
                    "value": str(meter_value['voltage']),
                    "format": "Raw",
                    "measurand": "Voltage",
                    "unit": "V"
                }
                current_sampled_value = {
                    "value": str(meter_value['current']),
                    "format": "Raw",
                    "measurand": "Current.Import",
                    "unit": "A"
                }
                power_sampled_value = {
                    "value": str(meter_value['power']),
                    "format": "Raw",
                    "measurand": "Power.Active.Import",  # Added power measurand
                    "unit": "W"  # Unit for power is Watts (W)
                }
                request = call.MeterValuesPayload(
                    connector_id=connector_id,
                    transaction_id=transaction['transaction_id'],
                    meter_value=[{
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [energy_sampled_value]
                    }, {
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [voltage_sampled_value]
                    }, {
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [current_sampled_value]
                    }, {
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [power_sampled_value]  # Added power sampled value
                    }]
                )
                response = await self.call(request)
                print(response)
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
            self.connector_status[connector_id]['status'] = 'Unavailable'
            self.connector_status[connector_id]['notification_sent'] = False
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
                                    # Update energy based on power and time interval
                                    self.meter[key]['energy'] += values['power'] * sleep_interval / 3600
                                    values['energy'] = self.meter[key]['energy']
                                self.meter[key] = values
                            # print(self.meter)
                    await asyncio.sleep(sleep_interval)
            except asyncio.CancelledError:
                print("Serial reading cancelled.")
            finally:
                await asyncio.sleep(sleep_interval)
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
