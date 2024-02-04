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
                            )

import json

logging.basicConfig(level=logging.INFO)

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
    async def handle_get_configuration(self):
        # requested_keys = request.key
        configuration = {}

        configuration = {k: {"key":str(k),"value": str(v),"readonly":True} for k, v in self.config.items()}

        return call_result.GetConfigurationPayload(
            configuration_key=list(configuration.values())
        )

    @on(Action.ChangeConfiguration)
    async def handle_set_configuration(self,request):
        unknown_keys = []
        for key_value in request.key_value:
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

    @on('UpdateFirmware')
    async def on_update_firmware(self, request):
        url = request.location
        firmware_file = 'new_firmware.py'

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
            "ws://localhost:80/34829732A7B0", subprotocols=["ocpp1.6"]
        ) as ws:
            cp_instance = ChargePoint("34829732A7B0", ws)
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
