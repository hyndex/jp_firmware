import asyncio
import logging
import websockets
import random
from datetime import datetime
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call
from ocpp.v16.enums import (
    RegistrationStatus,
    AuthorizationStatus,
    ConnectorStatus,
    ResetType,
    ResetStatus
)
from ocpp.routing import on

logging.basicConfig(level=logging.INFO)

class ChargePoint(cp):
    def __init__(self, id, connection, config):
        super().__init__(id, connection)
        self.config = config
        self.connectors_status = {
            i: ConnectorStatus.available for i in range(1, self.config["NumberOfConnectors"] + 1)
        }
        self.active_transactions = {}
        self.meter_values = {
            i: 0 for i in range(1, self.config["NumberOfConnectors"] + 1)
        }
        self.running_tasks = set()
        self.connected = False
        self.reconnecting = False

    async def start(self):
        await super().start()
        self.running_tasks.add(asyncio.create_task(self.send_periodic_heartbeat()))
        self.running_tasks.add(asyncio.create_task(self.simulate_connector_status_changes()))

    async def send_boot_notification(self, retries=0):
        if retries > self.config["MaxBootNotificationRetries"]:
            logging.error("Max boot notification retries reached. Giving up.")
            return

        request = call.BootNotificationPayload(
            charge_point_model="Wallbox XYZ",
            charge_point_vendor="anewone",
        )
        try:
            response = await self.call(request)
            if response.status == RegistrationStatus.accepted:
                self.connected = True
                logging.info("Connected to central system.")
            else:
                logging.warning("Boot notification not accepted. Retrying...")
                await asyncio.sleep(self.config["BootNotificationRetryInterval"])
                await self.send_boot_notification(retries + 1)
        except Exception as e:
            logging.error(f"Error sending boot notification: {e}. Retrying...")
            await asyncio.sleep(self.config["BootNotificationRetryInterval"])
            await self.send_boot_notification(retries + 1)

    async def authorize(self, id_tag):
        request = call.AuthorizePayload(id_tag=id_tag)
        response = await self.call(request)
        return response.id_tag_info.status == AuthorizationStatus.accepted

    async def start_transaction(self, connector_id, id_tag):
        if self.connectors_status[connector_id] == ConnectorStatus.available:
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
                self.connectors_status[connector_id] = ConnectorStatus.occupied
                asyncio.create_task(self.send_periodic_meter_values(connector_id, transaction_id))
                logging.info(
                    f"Transaction started on connector {connector_id} with Transaction ID: {transaction_id}"
                )
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
            request = call.StopTransactionPayload(
                meter_stop=meter_stop,
                timestamp=datetime.utcnow().isoformat(),
                transaction_id=transaction_id,
            )
            await self.call(request)
            self.connectors_status[connector_id] = ConnectorStatus.available
            logging.info(f"Transaction {transaction_id} stopped on connector {connector_id}")
            return True
        else:
            logging.warning(f"No active transaction found on connector {connector_id}")
            return False

    async def send_periodic_meter_values(self, connector_id, transaction_id):
        while connector_id in self.active_transactions:
            try:
                await asyncio.sleep(self.config["MeterValueSampleInterval"])
                self.meter_values[connector_id] += random.uniform(0.5, 2.0)  # More realistic increment
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
            except Exception as e:
                logging.error(f"Error sending meter values: {e}")

    async def simulate_connector_status_changes(self):
        while True:
            await asyncio.sleep(random.randint(5, 30))  # Randomize time for status change simulation
            for connector_id in self.connectors_status:
                # Realistic status transitions
                current_status = self.connectors_status[connector_id]
                if current_status == ConnectorStatus.available:
                    if random.random() < 0.2:
                        self.connectors_status[connector_id] = ConnectorStatus.unavailable
                elif current_status == ConnectorStatus.unavailable:
                    if random.random() < 0.5:
                        self.connectors_status[connector_id] = ConnectorStatus.available

    async def handle_reset(self, request):
        reset_type = request.type
        logging.info(f"Received {reset_type} reset request.")

        if reset_type == ResetType.soft:
            # Implement soft reset logic here
            logging.info("Performing soft reset.")
        elif reset_type == ResetType.hard:
            # Implement hard reset logic here
            logging.info("Performing hard reset.")

        return call.ResetPayload(
            status=ResetStatus.accepted
        )

    async def handle_get_configuration(self, request):
        requested_keys = request.key
        configuration = {}

        if not requested_keys:
            # Return all configuration settings
            configuration = {k: {"value": str(v)} for k, v in self.config.items()}
        else:
            # Return only the requested configuration settings
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
                # Update the configuration setting
                self.config[key] = value
            else:
                # Key not found in the configuration
                unknown_keys.append(key)

        return call.SetConfigurationPayload(
            unknown_key=unknown_keys
        )

    @on('RemoteStartTransaction')
    async def handle_remote_start_transaction(self, request):
        connector_id = request.connector_id
        id_tag = request.id_tag
        if connector_id in self.connectors_status and self.connectors_status[connector_id] == ConnectorStatus.available:
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
        # Logic to handle disconnection scenarios
        logging.warning("Disconnected from central system. Attempting to reconnect...")
        self.reconnecting = True
        # Implement reconnection logic here

    async def graceful_shutdown(self):
        logging.info("Shutting down simulator...")
        for task in self.running_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.connected:
            await self.ws.close()
        logging.info("Simulator successfully shut down.")

async def main():
    cp_instance = None
    try:
        config = {
            "HeartbeatInterval": 600,
            "MeterValueSampleInterval": 30,
            "NumberOfConnectors": 2,
            "BootNotificationRetryInterval": 10,
            "MaxBootNotificationRetries": 5
        }

        async with websockets.connect(
            "ws://localhost:9000/CP_1", subprotocols=["ocpp1.6"]
        ) as ws:
            cp_instance = ChargePoint("CP_1", ws, config)
            await cp_instance.start()
            await cp_instance.send_boot_notification()

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
        logging.info("Simulator stopped.")

if __name__ == "__main__":
    asyncio.run(main())
