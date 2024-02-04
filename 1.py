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
        self.load_config()
        self.pzem_ports = pzem_ports
        self.pzem_readers = {connector_id: PZEMMeterReader(port) for connector_id, port in pzem_ports.items()}
        self.relay_controllers = {connector_id: RelayController(pin) for connector_id, pin in relay_pins.items()}
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
        self.running_tasks.add(asyncio.create_task(self.send_periodic_heartbeat()))
        # self.running_tasks.add(asyncio.create_task(self.simulate_connector_status_changes()))


    async def send_periodic_heartbeat(self):
        while True:
            print('Sending Heartbeat')
            await asyncio.sleep(2)
            response = await self.call(call.HeartbeatPayload())
            print('Heartbeat Response', response)

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

    async def handle_disconnect(self):
        logging.warning("Disconnected from central system. Attempting to reconnect...")
        self.reconnecting = True
        # Implement reconnection logic here

    async def graceful_shutdown(self):
        logging.info("Shutting down charger...")
        # self.save_config()
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
            await cp_instance.send_boot_notification()
            await asyncio.gather(cp_instance.start(),)
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