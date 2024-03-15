import pigpio
import time

class HLW8032:
    def __init__(self, rx_pin, baudrate=4800):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise IOError("Unable to connect to pigpio daemon")
        self.rx_pin = rx_pin
        self.baudrate = baudrate
        self.pi.set_mode(self.rx_pin, pigpio.INPUT)
        self.pi.bb_serial_read_open(self.rx_pin, baudrate)  # Open bit-banging serial read
        self.data = {}

    def read_data(self):
        count, raw_data = self.pi.bb_serial_read(self.rx_pin)
        if count >= 24:
            if self.is_data_valid(raw_data):
                self.parse_data(raw_data)
            else:
                print("Invalid data received")

    def parse_data(self, raw_data):
        try:
            # Parse the raw data into meaningful values
            self.data = {
                'state_reg': raw_data[0],
                'check_reg': raw_data[1],
                'voltage_parameter_reg': int.from_bytes(raw_data[2:5], byteorder='big'),
                'voltage_reg': int.from_bytes(raw_data[5:8], byteorder='big'),
                'current_parameter_reg': int.from_bytes(raw_data[8:11], byteorder='big'),
                'current_reg': int.from_bytes(raw_data[11:14], byteorder='big'),
                'power_parameter_reg': int.from_bytes(raw_data[14:17], byteorder='big'),
                'power_reg': int.from_bytes(raw_data[17:20], byteorder='big'),
                'data_update_reg': raw_data[20],
                'pf_reg': int.from_bytes(raw_data[21:23], byteorder='big'),
                'checksum_reg': raw_data[23]
            }
        except Exception as e:
            print(f"Error parsing data: {e}")

    def is_data_valid(self, raw_data):
        checksum = sum(raw_data[:-1]) & 0xFF  # Calculate checksum of all bytes except the last one
        return checksum == raw_data[-1]  # Compare with the last byte (checksum byte)

    def get_data(self):
        return self.data

    def close(self):
        self.pi.bb_serial_read_close(self.rx_pin)  # Close bit-banging serial read
        self.pi.stop()

# Usage example
if __name__ == '__main__':
    hlw8032 = HLW8032(rx_pin=25)  # Set the RX pin as needed
    try:
        while True:
            hlw8032.read_data()
            data = hlw8032.get_data()
            if data:
                print("Voltage:", data.get('voltage_reg'))
                print("Current:", data.get('current_reg'))
                print("Power:", data.get('power_reg'))
            # time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        hlw8032.close()
