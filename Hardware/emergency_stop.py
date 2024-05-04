import pigpio
import asyncio
import logging

class EmergencyStopMonitor:
    def __init__(self, callback, pin=17):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Failed to connect to pigpio daemon")
        self.pin = pin
        self.callback = callback
        self.pi.set_mode(self.pin, pigpio.INPUT)
        self.pi.set_pull_up_down(self.pin, pigpio.PUD_DOWN)
        self.last_state = None

    async def start(self):
        logging.info("Starting emergency stop monitor.")
        try:
            while True:
                current_state = self.pi.read(self.pin)
                if current_state != self.last_state:
                    self.last_state = current_state
                    if current_state == 1:
                        logging.info("Emergency stop signal detected.")
                        await self.callback()
                await asyncio.sleep(1)
        finally:
            self.pi.stop()

    def __del__(self):
        self.pi.stop()
