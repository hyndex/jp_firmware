import pigpio
import logging
import time

# GPIO Pins for Emergency Stop Condition
EMERGENCY_STOP_PIN1 = 5  # Set as output
EMERGENCY_STOP_PIN2 = 6  # Set as input

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EmergencyStopMonitor:
    def __init__(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            logging.error("pigpio daemon is not running. Emergency stop monitor cannot start.")
            raise RuntimeError("pigpio daemon is not running")
        
        self.setup_pins()

    def setup_pins(self):
        # Set PIN1 as output, initially LOW
        self.pi.set_mode(EMERGENCY_STOP_PIN1, pigpio.OUTPUT)
        self.pi.write(EMERGENCY_STOP_PIN1, 0)  # Send LOW signal

        # Set PIN2 as input with pull-up (expecting to be pulled low by pressing the switch)
        self.pi.set_mode(EMERGENCY_STOP_PIN2, pigpio.INPUT)
        self.pi.set_pull_up_down(EMERGENCY_STOP_PIN2, pigpio.PUD_UP)

    def read_pins(self):
        while True:
            # Read PIN2 to see if it's LOW (indicating the switch is closed and connecting PIN1 to PIN2)
            if self.pi.read(EMERGENCY_STOP_PIN2) == 0:
                print("Switch CLOSED")
            else:
                print("Switch OPEN")
            time.sleep(0.1)

def main():
    logging.info("Starting emergency stop monitor")
    monitor = EmergencyStopMonitor()
    monitor.read_pins()

if __name__ == "__main__":
    main()
