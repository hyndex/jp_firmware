import pigpio
import logging
import time

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
            # Removed the glitch filter and callback since we are polling

    def read_pins(self):
        while True:
            for pin in self.stop_pins:
                if self.pi.read(pin):
                    print("ON")
                else:
                    print("OFF")
            time.sleep(0.1)

def main():
    logging.info("Starting emergency stop monitor")
    monitor = EmergencyStopMonitor([EMERGENCY_STOP_PIN1, EMERGENCY_STOP_PIN2])
    monitor.read_pins()

if __name__ == "__main__":
    main()
