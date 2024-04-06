import asyncio
import pigpio
import logging

# GPIO Pins for Emergency Stop Condition
EMERGENCY_STOP_PIN1 = 5  # Example GPIO pin number for the first emergency stop switch
EMERGENCY_STOP_PIN2 = 6  # Example GPIO pin number for the second emergency stop switch

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EmergencyStopMonitor:
    def __init__(self, stop_pins):
        self.stop_pins = stop_pins
        self.pi = pigpio.pi()
        if not self.pi.connected:
            logging.error("pigpio daemon is not running. Emergency stop monitor cannot start.")
            raise RuntimeError("pigpio daemon is not running")

        self.setup_pins()

    def setup_pins(self):
        for pin in self.stop_pins:
            self.pi.set_mode(pin, pigpio.INPUT)
            self.pi.set_pull_up_down(pin, pigpio.PUD_DOWN)
            self.pi.set_glitch_filter(pin, 100)  # Set a glitch filter to debounce
            self.pi.callback(pin, pigpio.EITHER_EDGE, self.emergency_stop_callback)

    def emergency_stop_callback(self, gpio, level, tick):
        # This function is called whenever an emergency stop switch is toggled
        logging.info(f"Emergency stop triggered via GPIO pin {gpio}. Level: {level}, Tick: {tick}")
        # Place your emergency stop handling code here. For example, you might want to:
        # - Stop all ongoing processes
        # - Turn off relays or other hardware
        # - Send notifications

def main():
    logging.info("Starting emergency stop monitor")
    monitor = EmergencyStopMonitor([EMERGENCY_STOP_PIN1, EMERGENCY_STOP_PIN2])
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logging.info("Emergency stop monitor stopped by the user.")

if __name__ == "__main__":
    main()
