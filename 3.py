import asyncio
import logging
import subprocess
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from ocpp.routing import on
from ocpp.v16.enums import (RegistrationStatus, AuthorizationStatus,
                            ConfigurationStatus, ResetType, ResetStatus, Action)
from ocpp.v16 import ChargePoint as cp, call, call_result
try:
    import websockets
except ModuleNotFoundError:
    print("This example relies on the 'websockets' package.")
    print("Please install it by running:")
    print()
    print(" $ pip install websockets")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)


class RelayController:
    def __init__(self, relay_pin):
        self.relay_pin = relay_pin

    def open_relay(self):
        print('Charging Started')

    def close_relay(self):
        print('Charging Stopped')


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
            

    def get_relay_pins(self):
        # Return a dictionary of connector IDs and their corresponding relay pins
        # Example: {1: 17, 2: 27}
        # You need to define this according to your setup
        return {1: 17, 2: 27}
    
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.config_file = "config.json"
        self.load_config()
        self.start_time = datetime.utcnow()
        # Initialize RelayControllers for each connector
        self.relay_controllers = {connector_id: RelayController(relay_pin) 
                                  for connector_id, relay_pin in self.get_relay_pins().items()}
        
        # Initialize active transactions
        self.active_transactions = {}
        # self.active_transactions[1] = {
        #     "transaction_id": 1616112820,
        #     "connector_id": 1, 
        #     "id_tag": 'CBS',
        #     "meter_start": 0
        # }

        print('Charger Done')


    def get_meter_value(self, connector_id):
        time_diff = datetime.utcnow() - self.start_time
        meter_value = time_diff.total_seconds() / 10
        return {"voltage":220, "current":16, "power":meter_value}

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
            await asyncio.sleep(2)
            request = call.HeartbeatPayload()
            response = await self.call(request)
            print(f"Heartbeat sent at {datetime.now()}: {response}")

    async def authorize(self, id_tag):
        request = call.AuthorizePayload(id_tag=id_tag)
        response = await self.call(request)
        return response.id_tag_info.status == AuthorizationStatus.accepted

    @on(Action.GetConfiguration)
    async def handle_get_configuration(self, **kwargs):
        request = {}
        requested_keys = kwargs.get('key', False)
        configuration = {}

        if not requested_keys:
            configuration = {k: {"key": str(k), "value": str(v), "readonly": True} for k, v in self.config.items()}
        else:
            for key in requested_keys:
                if key in self.config:
                    configuration[key] = {
                        "key": str(key),
                        "value": str(self.config[key]),
                        "readonly": True
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

    async def send_periodic_meter_values(self):
        await asyncio.sleep(5)
        while True:
            for connector_id, transaction in self.active_transactions.items():
                meter_value = self.get_meter_value(connector_id)
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
                await asyncio.sleep(self.config.get("MeterValueSampleInterval", 60))

    async def start_transaction(self, connector_id, id_tag):
        if connector_id not in self.active_transactions:
            meter_start = self.get_meter_value()
            request = call.StartTransactionPayload(
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=meter_start,
                timestamp=datetime.utcnow().isoformat()
            )
            response = await self.call(request)
            if response.id_tag_info.status == AuthorizationStatus.accepted:
                transaction_id = response.transaction_id
                transaction = {
                    "transaction_id": transaction_id,
                    "connector_id": connector_id, 
                    "id_tag": id_tag,
                    "meter_start": meter_start
                }

                self.active_transactions[connector_id] = transaction

                self.relay_controllers[connector_id].open_relay()
                print(f"Transaction {transaction_id} started on connector {connector_id}")
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
            meter_stop = self.get_meter_value()
            request = call.StopTransactionPayload(
                meter_stop=meter_stop,
                timestamp=datetime.utcnow().isoformat(),
                transaction_id=transaction_id
            )
            await self.call(request)
            self.relay_controllers[connector_id].close_relay()
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
        logging.info("Charger successfully shut down.")

    @on(Action.Reset)
    async def handle_reset(self, **kwargs):
        reset_type = kwargs.type
        logging.info(f"Received {reset_type} reset request.")

        call_result.ResetPayload(
            status=ResetStatus.accepted
        )

        self.graceful_shutdown()

        if reset_type == ResetType.soft:
            logging.info("Performing soft reset.")
            subprocess.run(["sudo", "reboot"], check=True)

        elif reset_type == ResetType.hard:
            logging.info("Performing hard reset.")
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


async def main():
    cp_instance = None
    try:
        async with websockets.connect(
                "ws://localhost:80/34829732A7B0", subprotocols=["ocpp1.6"]
        ) as ws:
            cp_instance = ChargePoint("34829732A7B0", ws)
            await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification(), cp_instance.heartbeat(), cp_instance.send_periodic_meter_values())
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
