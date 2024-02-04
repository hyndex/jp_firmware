import asyncio
import logging
from datetime import datetime

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
from ocpp.v16 import call
from ocpp.v16.enums import RegistrationStatus

logging.basicConfig(level=logging.INFO)
import json

def get_relay_pins():
        return {1: 17, 2: 27}


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
    async def send_boot_notification(self):
        request = call.BootNotificationPayload(
            charge_point_model="Optimus", charge_point_vendor="The Mobility House"
        )
        response = await self.call(request)

        if response.status == RegistrationStatus.accepted:
            print("Connected to central system.")

    def load_config(self):
        try:
            with open(self.config_file, 'r') as file:
                data = json.load(file)
                self.config = data
                self.active_transactions = data.get("active_transactions", {})
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Failed to load config: {e}")
            self.config = {"NumberOfConnectors": 2}

    def set_data(self):
        self.config_file = "config.json"
        self.load_config()
        self.start_time = datetime.utcnow()
        # Initialize RelayControllers for each connector
        self.relay_controllers = {connector_id: RelayController(relay_pin) 
                                  for connector_id, relay_pin in get_relay_pins().items()}
        
        # Initialize active transactions
        self.active_transactions = {}


    async def heartbeat(self):
        while True:
            await asyncio.sleep(2)  # wait for 2 seconds
            request = call.HeartbeatPayload()
            response = await self.call(request)
            print(f"Heartbeat sent at {datetime.now()}: {response}")

async def main():
    async with websockets.connect(
                "ws://csms.saikia.dev:8180/steve/websocket/CentralSystemService/test1", subprotocols=["ocpp1.6"]
        ) as ws:
        cp_instance = ChargePoint("test1", ws)
        cp_instance.set_data()
        await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat())

if __name__ == "__main__":
    asyncio.run(main())
