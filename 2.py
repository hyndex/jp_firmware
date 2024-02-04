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
                            )

import json
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)


class RelayController:
    def __init__(self, relay_pin):
        self.relay_pin = relay_pin
        # GPIO.setmode(GPIO.BCM)
        # GPIO.setup(self.relay_pin, GPIO.OUT)
        # GPIO.output(self.relay_pin, GPIO.LOW)  # Assume LOW means relay is off

    def open_relay(self):
        print('Charging Started')
        # GPIO.output(self.relay_pin, GPIO.HIGH)  # Turn relay on

    def close_relay(self):
        print('Charging Stopped')
        # GPIO.output(self.relay_pin, GPIO.LOW)  # Turn relay off


class ChargePoint(cp):
    def load_config(self):
        try:
            with open(self.config_file, 'r') as file:
                data = json.load(file)
                self.config = data
                self.active_transactions = data.get("active_transactions", {})
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Failed to load config: {e}")
            self.config = {"NumberOfConnectors": 2}
            self.active_transactions = {}

    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.config_file = "config.json"
        self.load_config()
        self.start_time = datetime.utcnow()

    def get_meter_value(self):
        # Calculate the time difference in seconds
        time_diff = datetime.utcnow() - self.start_time
        # Convert time difference to seconds and divide by 10 to get the meter value
        meter_value = time_diff.total_seconds() / 10
        return meter_value

    async def send_boot_notification(self):
        request = call.BootNotificationPayload(
            charge_point_model="Optimus", charge_point_vendor="The Mobility House"
        )

        await asyncio.sleep(2)
        response = await self.call(request)

        if response.status == RegistrationStatus.accepted:
            print("Connected to central system.")

    async def heartbeat(self):
        while True:
            await asyncio.sleep(2)  # wait for 2 seconds
            request = call.HeartbeatPayload()
            response = await self.call(request)
            print(f"Heartbeat sent at {datetime.now()}: {response}")

    async def authorize(self, id_tag):
        request = call.AuthorizePayload(id_tag=id_tag)
        response = await self.call(request)
        return response.id_tag_info.status == AuthorizationStatus.accepted

    @on(Action.GetConfiguration)
    async def handle_get_configuration(self, **kwargs):
        request={}
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
        unknown_keys = []
        for key_value in kwargs.key_value:
            key = key_value.key
            value = key_value.value
            if key in self.config:
                self.config[key] = value
                self.save_config()
            else:
                unknown_keys.append(key)

        return call_result.ChangeConfigurationPayload(
            status=ConfigurationStatus.accepted
        )


    async def send_periodic_meter_values(self, connector_id, transaction_id):
        while connector_id in self.active_transactions:
            meter_value = self.get_meter_value()
            sampled_value = {
                "value": str(meter_value),
                "context": "Sample.Periodic",
                "format": "Raw",
                "measurand": "Energy.Active.Import.Register",
                "location": "EV",
                "unit": "Wh"
            }

            request = call.MeterValuesPayload(
                connector_id=connector_id,
                transaction_id=transaction_id,
                meter_value=[{
                    "timestamp": datetime.utcnow().isoformat(),
                    "sampled_value": [sampled_value]
                }]
            )
            await self.call(request)
            await asyncio.sleep(self.config.get("MeterValueSampleInterval", 60))  # Default to 60 seconds


    async def start_transaction(self, connector_id, id_tag):
        if connector_id not in self.active_transactions:
            meter_start = self.get_meter_value()  # You need to implement this method
            request = call.StartTransactionPayload(
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=meter_start,
                timestamp=datetime.utcnow().isoformat()
            )
            response = await self.call(request)
            if response.id_tag_info.status == AuthorizationStatus.accepted:
                transaction_id = response.transaction_id
                self.active_transactions[connector_id] = transaction_id
                self.relay_controllers[connector_id].open_relay()  # Start charging
                print(f"Transaction {transaction_id} started on connector {connector_id}")
                asyncio.create_task(self.send_periodic_meter_values(connector_id, transaction_id))
                return True
            else:
                print(f"Start transaction denied for ID Tag: {id_tag}")
                return False
        else:
            print(f"Connector {connector_id} is already in use")
            return False

    async def stop_transaction(self, connector_id):
        if connector_id in self.active_transactions:
            transaction_id = self.active_transactions.pop(connector_id)
            meter_stop = self.get_meter_value()  # You need to implement this method
            request = call.StopTransactionPayload(
                meter_stop=meter_stop,
                timestamp=datetime.utcnow().isoformat(),
                transaction_id=transaction_id
            )
            await self.call(request)
            self.relay_controllers[connector_id].close_relay()  # Stop charging
            print(f"Transaction {transaction_id} stopped on connector {connector_id}")
            return True
        else:
            print(f"No active transaction found on connector {connector_id}")
            return False
        

    def save_config(self):
        with open(self.config_file, 'w') as file:
            json.dump(self.config, file)

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
        # GPIO.cleanup()  # Clean up GPIO pins
        logging.info("Charger successfully shut down.")


    @on(Action.Reset)
    async def handle_reset(self, **kwargs):
        reset_type = kwargs.type
        logging.info(f"Received {reset_type} reset request.")

        call_result.ResetPayload(
            status=ResetStatus.accepted
        )

        self. graceful_shutdown()

        if reset_type == ResetType.soft:
            logging.info("Performing soft reset.")
            # Soft reset - typically a graceful restart
            subprocess.run(["sudo", "reboot"], check=True)

        elif reset_type == ResetType.hard:
            logging.info("Performing hard reset.")
            # Hard reset - immediate reboot without waiting for processes to close
            subprocess.run(["sudo", "reboot", "-f"], check=True)

        return 
    
    @on('UpdateFirmware')
    async def on_update_firmware(self, **kwargs):
        url = kwargs.location
        firmware_file = f'new_firmware_{str(datetime.now())}.py'

        if self.download_firmware(url, firmware_file):
            self.apply_firmware_update(firmware_file)
        else:
            logging.error('Firmware download failed.')

    def download_firmware(self, url, destination):
        try:
            response = requests.get(url, timeout=60)  # Timeout to avoid long blocking
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
            # Success: The script won't reach here
        except subprocess.CalledProcessError:
            # Revert to old firmware
            os.rename(backup_firmware, current_firmware)
            subprocess.run(['python3', current_firmware])


async def main():
    cp_instance=None
    try:
        async with websockets.connect(
                "ws://csms.saikia.dev:8180/steve/websocket/CentralSystemService/test1", subprotocols=["ocpp1.6"]
        ) as ws:
            cp_instance = ChargePoint("test1", ws)
            await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat())
    except KeyboardInterrupt:
        if cp_instance:
            await cp_instance.graceful_shutdown()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        if cp_instance:
            await cp_instance.handle_disconnect()
    finally:
        logging.info("Charger stopped.")
if __name__ == "__main__":
    asyncio.run(main())
