import asyncio
import logging
import websockets
import random
import json
import serial
import struct
import os
import subprocess
import requests 
from datetime import datetime
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call
from ocpp.v16.enums import (
    RegistrationStatus,
    AuthorizationStatus,
    ChargePointStatus,
    ResetType,
    ResetStatus
)
from ocpp.routing import on
from pymodbus.client import ModbusSerialClient as ModbusClient
from pymodbus.exceptions import ModbusIOException

logging.basicConfig(level=logging.INFO)


class PZEMMeterReader:
    def __init__(self, serial_port):
        self.client = ModbusClient(method='rtu', port=serial_port, baudrate=9600, stopbits=1, bytesize=8, parity='N', timeout=1)


    def connect(self):
        try:
            if not self.client.connect():
                logging.error(f"Failed to connect to PZEM module on {self.serial_port}")
        except Exception as e:
            logging.error(f"Failed to connect to PZEM module on {self.serial_port}: {e}")

    def read_power_consumption(self):
        try:
            result = self.client.read_input_registers(address=0x0000, count=10, unit=1)
            if result.isError():
                raise ValueError("Error reading from PZEM module")
            voltage = result.registers[0] / 10.0
            current = (result.registers[1] + (result.registers[2] << 16)) / 1000.0
            power = (result.registers[3] + (result.registers[4] << 16)) / 10.0
            energy = (result.registers[5] + (result.registers[6] << 16)) / 1.0
            frequency = result.registers[7] / 10.0
            pf = result.registers[8] / 100.0
            return {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
                "frequency": frequency,
                "pf": pf
            }
        except Exception as e:
            logging.error(f"Error reading from PZEM module: {e}")
            return None

    def close(self):
        self.client.close()


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
    def __init__(self, id, connection, config_file, pzem_ports, relay_pins):
        super().__init__(id, connection)
        self.config_file = config_file
        self.pzem_ports = pzem_ports
        self.pzem_readers = {connector_id: PZEMMeterReader(port) for connector_id, port in pzem_ports.items()}
        self.relay_controllers = {connector_id: RelayController(pin) for connector_id, pin in relay_pins.items()}
        self.load_config()
        self.running_tasks = set()
        self.connected = False
        self.reconnecting = False


    def load_config(self):
        try:
            with open(self.config_file, 'r') as file:
                data = json.load(file)
                self.config = data#.get("data", {})
                self.active_transactions = data.get("active_transactions", {})
                self.meter_values = data.get("meter_values", {})
                self.connectors_status = data.get("connectors_status", {})
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Failed to load config: {e}")
            self.config = {"NumberOfConnectors": 2}
            self.active_transactions = {}
            self.meter_values = {i: 0 for i in range(1, self.config["NumberOfConnectors"] + 1)}
            self.connectors_status = {i: ChargePointStatus.available for i in range(1, self.config["NumberOfConnectors"] + 1)}

    def save_config(self):
        try:
            with open(self.config_file, 'w') as file:
                json.dump({
                    "config": self.config,
                    "active_transactions": self.active_transactions,
                    "meter_values": self.meter_values,
                    "connectors_status": self.connectors_status
                }, file)
        except IOError as e:
            logging.error(f"Failed to save config: {e}")

    async def start(self):
        await super().start()
        self.load_config()
        self.running_tasks.add(asyncio.create_task(self.send_periodic_heartbeat()))
        # self.running_tasks.add(asyncio.create_task(self.simulate_connector_status_changes()))


    async def send_periodic_heartbeat(self):
        while True:
            print('Sending Heartbeat')
            await asyncio.sleep(self.config["HeartbeatInterval"])
            await self.call(call.HeartbeatPayload())

    async def send_boot_notification(self, retries=0):
        self.load_config()


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

        async def authorize(self, id_tag):
            request = call.AuthorizePayload(id_tag=id_tag)
            response = await self.call(request)
            return response.id_tag_info.status == AuthorizationStatus.accepted

        async def start_transaction(self, connector_id, id_tag):
            if self.connectors_status[connector_id] == ChargePointStatus.available:
                meter_start = self.meter_values[connector_id]
                request = call.StartTransactionPayload(
                    connector_id=connector_id,
                    id_tag=id_tag,
                    meter_start=meter_start,
                    timestamp=datetime.utcnow().isoformat(),
                )
                response = await self.call(request)
                if response.id_tag_info.status == AuthorizationStatus.accepted:
                    transaction_id = response.transaction_id
                    self.active_transactions[connector_id] = transaction_id
                    self.connectors_status[connector_id] = ChargePointStatus.charging
                    self.relay_controllers[connector_id].open_relay()  # Open relay to start charging
                    self.pzem_readers[connector_id].connect()
                    logging.info(
                        f"Transaction started on connector {connector_id} with Transaction ID: {transaction_id}"
                    )
                    self.save_config()
                    asyncio.create_task(self.send_periodic_meter_values(connector_id, transaction_id))
                    return True
                else:
                    logging.warning(f"Start transaction denied for ID Tag: {id_tag}")
                    return False
            else:
                logging.warning(f"Connector {connector_id} is not available")
                return False

        async def stop_transaction(self, connector_id):
            if connector_id in self.active_transactions:
                transaction_id = self.active_transactions.pop(connector_id)
                meter_stop = self.meter_values[connector_id]
                request = call.StopTransaction

                call.StopTransactionPayload(
                    meter_stop=meter_stop,
                    timestamp=datetime.utcnow().isoformat(),
                    transaction_id=transaction_id,
                )
                await self.call(request)
                self.relay_controllers[connector_id].close_relay()  # Close relay to stop charging
                self.pzem_readers[connector_id].close()
                self.connectors_status[connector_id] = ChargePointStatus.available
                logging.info(f"Transaction {transaction_id} stopped on connector {connector_id}")
                self.save_config()
                return True
            else:
                logging.warning(f"No active transaction found on connector {connector_id}")
                return False

        async def send_periodic_meter_values(self, connector_id, transaction_id):
            while connector_id in self.active_transactions:
                try:
                    await asyncio.sleep(self.config.get("MeterValueSampleInterval", 30))
                    pzem_reading = self.pzem_readers[connector_id].read_power_consumption()
                    if pzem_reading is not None:
                        self.meter_values[connector_id] += pzem_reading
                    await self.call(
                        call.MeterValuesPayload(
                            connector_id=connector_id,
                            transaction_id=transaction_id,
                            meter_value=[
                                {
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "sampled_value": [
                                        {"value": str(self.meter_values[connector_id]), "context": "Sample.Periodic"}
                                    ],
                                }
                            ],
                        )
                    )
                    self.save_config()
                except Exception as e:
                    logging.error(f"Error sending meter values: {e}")

        async def simulate_connector_status_changes(self):
            while True:
                await asyncio.sleep(random.randint(5, 30))
                for connector_id in self.connectors_status:
                    current_status = self.connectors_status[connector_id]
                    if current_status == ChargePointStatus.available:
                        if random.random() < 0.2:
                            self.connectors_status[connector_id] = ChargePointStatus.unavailable
                    elif current_status == ChargePointStatus.unavailable:
                        if random.random() < 0.5:
                            self.connectors_status[connector_id] = ChargePointStatus.available

        async def handle_reset(self, request):
            reset_type = request.type
            logging.info(f"Received {reset_type} reset request.")

            if reset_type == ResetType.soft:
                logging.info("Performing soft reset.")
            elif reset_type == ResetType.hard:
                logging.info("Performing hard reset.")

            return call.ResetPayload(
                status=ResetStatus.accepted
            )

        async def handle_get_configuration(self, request):
            requested_keys = request.key
            configuration = {}

            if not requested_keys:
                configuration = {k: {"value": str(v)} for k, v in self.config.items()}
            else:
                for key in requested_keys:
                    if key in self.config:
                        configuration[key] = {"value": str(self.config[key])}

            return call.GetConfigurationPayload(
                configuration_key=list(configuration.values())
            )

        async def handle_set_configuration(self, request):
            settings = request.key_value
            unknown_keys = []

            for setting in settings:
                key, value = setting.key, setting.value
                if key in self.config:
                    self.config[key] = value
                else:
                    unknown_keys.append(key)

            return call.SetConfigurationPayload(
                unknown_key=unknown_keys
            )

        @on('RemoteStartTransaction')
        async def handle_remote_start_transaction(self, request):
            connector_id = request.connector_id
            id_tag = request.id_tag
            if connector_id in self.connectors_status and self.connectors_status[connector_id] == ChargePointStatus.available:
                return await self.start_transaction(connector_id, id_tag)
            else:
                logging.warning(f"Cannot start transaction: Connector {connector_id} is not available.")
                return call.RemoteStartTransactionPayload(
                    status='Rejected'
                )

        @on('RemoteStopTransaction')
        async def handle_remote_stop_transaction(self, request):
            transaction_id = request.transaction_id
            for connector_id, txn_id in self.active_transactions.items():
                if txn_id == transaction_id:
                    return await self.stop_transaction(connector_id)
            logging.warning(f"Transaction ID {transaction_id} not found.")
            return call.RemoteStopTransactionPayload(
                status='Rejected'
            )

        async def handle_disconnect(self):
            logging.warning("Disconnected from central system. Attempting to reconnect...")
            self.reconnecting = True
            # Implement reconnection logic here

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
    cp_instance = None
    try:
        config = {
            "HeartbeatInterval": 600,
            "MeterValueSampleInterval": 30,
            "NumberOfConnectors": 2,
            "BootNotificationRetryInterval": 10,
            "MaxBootNotificationRetries": 5,
            "Model":"BharatAC",
            "Vendor":"Chinmoy"

        }
        config_file = "config.json"
        
        # Define PZEM ports for each connector
        pzem_ports = {
            1: '/dev/ttyUSB0',
            2: '/dev/ttyUSB1',
            # Add more if needed
        }

        relay_pins = {
            1: 17,  # Replace with actual GPIO pin numbers
            2: 27,
            # Add more if needed
        }

        async with websockets.connect(
            "ws://localhost:80/34829732A7B0", subprotocols=["ocpp1.6"]
        ) as ws:
            cp_instance = ChargePoint("34829732A7B0", ws, config_file, pzem_ports, relay_pins)
            print('Server Connection Done')
            await asyncio.gather(cp_instance.start(), cp_instance.send_boot_notification())
            print('Boot notification done')


            while True:
                await asyncio.sleep(1)
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