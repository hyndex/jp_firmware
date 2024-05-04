import pigpio
import logging

class RelayController:
    def __init__(self, relay_pins):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")
        self.relay_pins = relay_pins  # Dictionary of relay pins
        for pin in relay_pins.values():
            self.pi.set_mode(pin, pigpio.OUTPUT)

    def activate_relay(self, relay_id):
        if relay_id in self.relay_pins:
            self.pi.write(self.relay_pins[relay_id], 1)
            logging.info(f"Relay {relay_id} activated on pin {self.relay_pins[relay_id]}.")

    def deactivate_relay(self, relay_id):
        if relay_id in self.relay_pins:
            self.pi.write(self.relay_pins[relay_id], 0)
            logging.info(f"Relay {relay_id} deactivated on pin {self.relay_pins[relay_id]}.")

    def deactivate_all_relays(self):
        for relay_id in self.relay_pins:
            self.deactivate_relay(relay_id)
            logging.info(f"All relays deactivated.")

    def __del__(self):
        self.pi.stop()
