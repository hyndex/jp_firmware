import asyncio
import logging
from action_handlers import on_update_firmware, on_clear_cache, handle_reset
from boot_notifications import send_boot_notification, heartbeat
from config_management import handle_get_configuration, handle_set_configuration
from status_handling import send_status_notification
from transaction_handling import start_transaction, stop_transaction, send_periodic_meter_values, remote_start_transaction, remote_stop_transaction
from ChargePoint.misc import load_json_config, save_json_config, initialize_csv
from ..Hardware.relay_control import RelayController
from ..Hardware.emergency_stop import EmergencyStopMonitor
from ..Hardware.lcd import update_lcd_line


class ChargePoint:
    def __init__(self, config_path='config.json'):
        self.config = load_json_config(config_path)
        self.read_only_parameters = set(self.config.get("ReadOnlyParameters", []))
        self.active_transactions = {}
        self.connector_status = {i: {"status": "Available", "error_code": "NoError", "notification_sent": False}
                                 for i in range(1, self.config.get("NumberOfConnectors", 2) + 1)}
        
        relay_pins = {i: pin for i, pin in enumerate(self.config.get("RelayPins", [17, 27, 22]), 1)}
        self.relay_controller = RelayController(relay_pins)
        self.emergency_stop_monitor = EmergencyStopMonitor(self.handle_emergency_stop)

        self.connected = False
        self.function_call_queue = asyncio.Queue()
        asyncio.create_task(self.process_function_calls())
        

    async def process_function_calls(self):
        while True:
            function_info = await self.function_call_queue.get()
            function, args, kwargs = function_info
            await function(*args, **kwargs)
            self.function_call_queue.task_done()


    async def update_specific_lcd_line(self, line_number, message):
        """
        Update a specific line on the LCD with the given message.
        :param line_number: The line number to update (1-4).
        :param message: The message to display on the line.
        """
        # Call the update_lcd_line function with the specific line and message
        update_lcd_line(line_number, message)

    async def boot_sequence(self):
        await send_boot_notification(self)
        asyncio.create_task(heartbeat(self))

    async def handle_emergency_stop(self):
        logging.info("Handling emergency stop...")
        self.relay_controller.deactivate_all_relays()

    async def update_firmware(self, url):
        await on_update_firmware(self, url, "firmware_updates/")

    async def clear_cache(self):
        await on_clear_cache(self)

    async def system_reset(self, reset_type):
        await handle_reset(self, reset_type)

    async def fetch_configuration(self):
        return await handle_get_configuration(self)

    async def update_configuration(self, key, value):
        return await handle_set_configuration(self, key, value)

    async def send_status_updates(self, connector_id):
        await send_status_notification(self, connector_id)

    async def remote_start(self, connector_id, id_tag):
        await self.function_call_queue.put((remote_start_transaction, [self, connector_id, id_tag], {}))

    async def remote_stop(self, transaction_id):
        await self.function_call_queue.put((remote_stop_transaction, [self, transaction_id], {}))

    async def handle_transactions(self, connector_id, id_tag):
        await self.function_call_queue.put((start_transaction, [self, connector_id, id_tag], {}))
        await asyncio.sleep(300)  # Simulate transaction duration
        await self.function_call_queue.put((stop_transaction, [self, connector_id, 'Remote'], {}))

    async def meter_values_loop(self):
        asyncio.create_task(send_periodic_meter_values(self))
