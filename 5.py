import asyncio
import logging
from datetime import datetime
import subprocess
import os
from ocpp.routing import on
from ocpp.v16.enums import Action
import requests
import time
try:
    import websockets
except ModuleNotFoundError:
    print("This example relies on the 'websockets' package.")
    print("Please install it by running: ")
    print()
    print(" $ pip install websockets")
    import sys
    sys.exit(1)

from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (RegistrationStatus
                            , AuthorizationStatus
                            , ConfigurationStatus
                            , ResetType
                            , ResetStatus
                            , ClearCacheStatus
                            , TriggerMessageStatus
                            , MessageTrigger
                            )

import json
from datetime import datetime, timedelta


logging.basicConfig(level=logging.INFO)


def get_relay_pins():
        return {1: 17, 2: 27}

start_time = datetime.now()

def get_meter_value():
        # Calculate the time difference in seconds
        time_diff = datetime.now() - start_time
        # Convert time difference to seconds and divide by 10 to get the meter value
        meter_value = time_diff.total_seconds() / 10
        return { "power":meter_value
            , "voltage":220
            , "current":16
        }

class RelayController:
    def __init__(self, relay_pin):
        self.relay_pin = relay_pin

    def open_relay(self):
        print('Charging Started')

    def close_relay(self):
        print('Charging Stopped')

def load_config(config_file):
    try:
        with open(config_file, 'r') as file:
            data = json.load(file)
            return data
        
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Failed to load config: {e}")
        return {"NumberOfConnectors": 2}

class ChargePoint(cp):

    ###########
    ## Non OCPP Functions
    ###########

    async def handle_disconnect(self):
        logging.warning("Disconnected from central system. Attempting to reconnect...")
        self.reconnecting = True

    async def graceful_shutdown(self):
        logging.info("Shutting down charger...")
        self.save_config()
        for task in self.running_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.connected:
            await self.ws.close()
        logging.info("Charger successfully shut down.")


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

    def reset_data(self):
        self.config_file = "config.json"
        self.load_config()
        self.start_time = datetime.utcnow()
        # Initialize RelayControllers for each connector
        self.relay_controllers = {connector_id: RelayController(relay_pin) 
                                  for connector_id, relay_pin in get_relay_pins().items()}
        
        self.active_transactions = {}

        self.function_call_queue = asyncio.Queue()
        asyncio.create_task(self.process_function_call_queue())


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

        os.rename(current_firmware, backup_firmware)
        os.rename(firmware_file, current_firmware)

        try:
            subprocess.run(['python3', current_firmware], check=True)
        except subprocess.CalledProcessError:
            os.rename(backup_firmware, current_firmware)
            subprocess.run(['python3', current_firmware])

    async def process_function_call_queue(self):
        while True:
            function_call = await self.function_call_queue.get()
            await function_call["function"](*function_call["args"], **function_call["kwargs"])
            self.function_call_queue.task_done()


    ###########
    ## Charger Originating commands
    ###########

    async def send_boot_notification(self, retries=0):

        if retries > self.config.get("MaxBootNotificationRetries", 5):
            logging.error("Max boot notification retries reached. Giving up.")
            return

        request = call.BootNotificationPayload(
            charge_point_model=self.config.get('Model'),
            charge_point_vendor=self.config.get('Vendor'),
        )
        
        logging.info(f"Sending BootNotification request: {request}")

        try:
            response = await self.call(request)
            logging.info(f"Boot notification response: {response}")  # Log the response

            if response.status == RegistrationStatus.accepted:
                self.connected = True
                logging.info("Connected to central system.")
                return 
            else:
                logging.warning("Boot notification not accepted. Retrying...")
                await asyncio.sleep(self.config.get("BootNotificationRetryInterval", 10))
                await self.send_boot_notification(retries + 1)
        except Exception as e:
            logging.error(f"Error sending boot notification: {e}. Retrying...")
            await asyncio.sleep(self.config.get("BootNotificationRetryInterval", 10))
            await self.send_boot_notification(retries + 1)



    async def heartbeat(self):
        while True:
            await asyncio.sleep(int(self.config.get('HeartbeatInterval'),30))  # wait for 2 seconds
            request = call.HeartbeatPayload()
            response = await self.call(request)
            logging.info(f"Heartbeat sent/recieve at {datetime.now()}: {response}")

    async def authorize(self, id_tag):
        request = call.AuthorizePayload(id_tag=id_tag)
        response = await self.call(request)
        return response.id_tag_info.status == AuthorizationStatus.accepted
    
    
    async def start_transaction(self, connector_id, id_tag):
        if connector_id not in self.active_transactions:
            meter_start = get_meter_value()

            authorize_response = await self.authorize(id_tag)
            if not authorize_response:
                logging.error(f"Authorization failed for idTag {id_tag}. Transaction not stopped.")
                return False
            
            request = call.StartTransactionPayload(
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=int(meter_start['power']),
                timestamp=datetime.utcnow().isoformat()
            )

            response = await self.call(request)
            transaction_id = response.transaction_id
            transaction = {
                "transaction_id": transaction_id,
                "connector_id": connector_id, 
                "id_tag": id_tag,
                "meter_start": int(meter_start['power']),
            }

            self.active_transactions[connector_id] = transaction

            self.relay_controllers[connector_id].open_relay()
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
            meter_stop = int(get_meter_value(connector_id)['power'] * 1000)

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

            return True
        else:
            logging.warning(f"No active transaction found on connector {connector_id}")
            return False


    async def send_periodic_meter_values(self):
        while True:
            for connector_id, transaction in self.active_transactions.items():
                meter_value = get_meter_value(connector_id)
                power_sampled_value = {
                    "value": str(meter_value['power']),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "EV",
                    "unit": "Wh"
                }

                voltage_sampled_value = {
                    "value": str(meter_value['voltage']),
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh"
                }

                current_sampled_value = {
                    "value": str(meter_value['current']),
                    "format": "Raw",
                    "measurand": "Voltage",
                    "unit": "V"
                }

                request = call.MeterValuesPayload(
                    connector_id=connector_id,
                    transaction_id=transaction['transaction_id'],
                    meter_value=[{
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [power_sampled_value]
                    },{
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [voltage_sampled_value]
                    },{
                        "timestamp": datetime.utcnow().isoformat(),
                        "sampled_value": [current_sampled_value]
                    }]
                )
                response = await self.call(request)
                print(response)
                await asyncio.sleep(self.config.get("MeterValueSampleInterval", 60))



    ###########
    ## Server Originating commands
    ###########

    @on(Action.TriggerMessage)
    async def on_trigger_message(self, **kwargs):
        requested_message = kwargs.get('requested_message')
        connector_id = kwargs.get('connector_id', None)

        if requested_message == MessageTrigger.BootNotification:
            await self.function_call_queue.put({
                "function": self.send_boot_notification,
                "args": [],
                "kwargs": {}
            })
            status = TriggerMessageStatus.accepted
        elif requested_message == MessageTrigger.Heartbeat:
            await self.function_call_queue.put({
                "function": self.heartbeat,
                "args": [],
                "kwargs": {}
            })
            status = TriggerMessageStatus.accepted
        else:
            status = TriggerMessageStatus.notImplemented

        return call_result.TriggerMessagePayload(
            status=status
        )
    
    @on(Action.UpdateFirmware)
    async def on_update_firmware(self, **kwargs):
        url = kwargs.location
        firmware_file = f'new_firmware_{str(datetime.now())}.py'

        if self.download_firmware(url, firmware_file):
            self.apply_firmware_update(firmware_file)
        else:
            logging.error('Firmware download failed.')

    @on(Action.ClearCache)
    async def on_clear_cache(self, **kwargs):
        self.reset_data()
        return call_result.ClearCachePayload(
                status=ClearCacheStatus.accepted
            ) 

    @on(Action.GetConfiguration)
    async def handle_get_configuration(self, **kwargs):
        requested_keys = kwargs.get('key',False)
        configuration = {}

        if not requested_keys:
            configuration = {k: {"key":str(k),"value": str(v),"readonly":True} for k, v in self.config.items()}

        else:
            for key in requested_keys:
                if key in self.config:
                    configuration[key] = {
                                            "key":str(key),
                                            "value": str(self.config[key]),
                                            "readonly":True
                                        }

        return call_result.GetConfigurationPayload(
                configuration_key=list(configuration.values())
            )

    @on(Action.ChangeConfiguration)
    async def handle_set_configuration(self, **kwargs):
        key = kwargs.get('key')
        value = kwargs.get('value')

        if key in self.config:
            self.config[key] = value
            self.save_config()
            return call_result.ChangeConfigurationPayload(
                status=ConfigurationStatus.accepted
            )
        else:
            return call_result.ChangeConfigurationPayload(
                status=ConfigurationStatus.rejected
            )

    @on(Action.UpdateFirmware)
    async def on_update_firmware(self, **kwargs):
        url = kwargs.location
        firmware_file = f'new_firmware_{str(datetime.now())}.py'

        if self.download_firmware(url, firmware_file):
            self.apply_firmware_update(firmware_file)
        else:
            logging.error('Firmware download failed.')
   
        
    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(self, **kwargs):
        id_tag = kwargs.get('id_tag')
        connector_id = kwargs.get('connector_id', 1)  # default to connector 1 if not specified

        if connector_id in self.active_transactions:
            print(f"Connector {connector_id} is already in use.")
            return call_result.RemoteStartTransactionPayload(status='Rejected')

        # Enqueue the start_transaction call
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
                await self.stop_transaction(connector_id, )
                return call_result.RemoteStopTransactionPayload(status='Accepted')

        print(f"Transaction ID {transaction_id} not found.")
        return call_result.RemoteStopTransactionPayload(status='Rejected')

    

async def main():
    async with websockets.connect(
                "ws://csms.saikia.dev:8180/steve/websocket/CentralSystemService/test1", subprotocols=["ocpp1.6"]
        ) as ws:
        cp_instance = ChargePoint("test1", ws)
        cp_instance.reset_data()
        await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat())

if __name__ == "__main__":
    asyncio.run(main())
