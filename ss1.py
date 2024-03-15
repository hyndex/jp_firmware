import pigpio
import time

class HLW8032:
    def __init__(self, pi, rx_pin):
        self.pi = pi
        self.rx_pin = rx_pin
        self.serial_data = []
        self.vf = 0
        self.cf = 0
        self.vol_r1 = 1880000  # 470K * 4 = 1880K
        self.vol_r2 = 1000     # 1K
        self.current_rf = 0.001  # 1 milliohm
        self.pi.set_mode(rx_pin, pigpio.INPUT)
        self.pi.bb_serial_read_open(rx_pin, 4800, 9)  # 9 bits (8 data + 1 parity)

    def begin(self):
        self.vf = self.vol_r1 / (self.vol_r2 * 1000.0)  # Calculate voltage coefficient
        self.cf = 1.0 / (self.current_rf * 1000.0)      # Calculate current coefficient

    def serial_read_loop(self):
        (count, data) = self.pi.bb_serial_read(self.rx_pin)
        if count > 0:
            # print(data)
            # Filter out zeros
            filtered_data = [byte for byte in data if byte != 0]
            self.serial_data.extend(filtered_data)
            while len(self.serial_data) >= 24:
                packet = self.serial_data[:24]
                self.process_data(packet)
                self.serial_data = self.serial_data[24:]

    def process_data(self, packet):
        hex_data = [hex(byte) for byte in packet]

        if packet[1] != 0x5A:
            return
        if not self.checksum(packet):
            return

        self.parse_data(packet)

    def parse_data(self, packet):
        # Convert hex strings to integers
        data = packet #[int(x, 16) for x in packet]

        # Voltage Parameter
        voltage_param = (data[4] << 16) + (data[5] << 8) + data[6]
        # Voltage Data
        voltage_data = (data[7] << 16) + (data[8] << 8) + data[9]
        # Calculate Voltage
        voltage = (voltage_param / voltage_data) * self.vf if voltage_data != 0 else 0

        # Current Parameter
        current_param = (data[10] << 16) + (data[11] << 8) + data[12]
        # Current Data
        current_data = (data[13] << 16) + (data[14] << 8) + data[15]
        # Calculate Current
        current = (current_param / current_data) * self.cf if current_data != 0 else 0

        # Power Parameter
        power_param = (data[16] << 16) + (data[17] << 8) + data[18]
        # Power Data
        power_data = (data[19] << 16) + (data[20] << 8) + data[21]
        # Calculate Power
        power = (power_param / power_data) * self.vf * self.cf if power_data != 0 else 0

        print(f"Voltage: {voltage:.2f} V")
        print(f"Current: {current:.2f} A")
        print(f"Power: {power:.2f} W")

    def checksum(self, packet):
        check = 0
        for i in range(2, 23):
            check += packet[i]
        print('A',check, packet[23])
        print('B',packet)
        return check == packet[23]

    def close(self):
        self.pi.bb_serial_read_close(self.rx_pin)

# Example usage
pi = pigpio.pi()
hlw8032 = HLW8032(pi, rx_pin=25)  # Adjust the RX pin as needed
hlw8032.begin()
try:
    while True:
        hlw8032.serial_read_loop()
        time.sleep(0.05)
finally:
    hlw8032.close()
    pi.stop()
