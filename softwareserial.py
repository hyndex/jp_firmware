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
            print(data)
            self.serial_data.extend(data)
            while len(self.serial_data) >= 24:
                packet = self.serial_data[:24]
                self.process_data(packet)
                self.serial_data = self.serial_data[24:]



    def parse_data(self, packet):
        # Convert hex strings to integers
        data = [int(x, 16) for x in packet]

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


    def process_data(self, packet):
        hex_data = [hex(byte) for byte in packet]
        a = 0
        if hex_data[1] == '0x5a':
            print('A', packet, len(packet))
            print('B', hex_data)
            a = 1

        if not self.checksum(packet):
            # if (a==1):
                # print('checksum exiting')

            return

        print('checksum successful')

        if packet[1] != 0x5A:
            # if (a==1):
                # print('exiting')
            return
        if not self.checksum(packet):
            return

        vol_par = (self.serial_data[2] << 16) + (self.serial_data[3] << 8) + self.serial_data[4]
        if self.serial_data[20] & 0x40:
            vol_data = (self.serial_data[5] << 16) + (self.serial_data[6] << 8) + self.serial_data[7]
            vol = (vol_par / vol_data) * self.vf
            print("Voltage:", vol, "V")

        current_par = (self.serial_data[8] << 16) + (self.serial_data[9] << 8) + self.serial_data[10]
        if self.serial_data[20] & 0x20:
            current_data = (self.serial_data[11] << 16) + (self.serial_data[12] << 8) + self.serial_data[13]
            current = (current_par / current_data) * self.cf
            print("Current:", current, "A")

        power_par = (self.serial_data[14] << 16) + (self.serial_data[15] << 8) + self.serial_data[16]
        if self.serial_data[20] & 0x10:
            power_data = (self.serial_data[17] << 16) + (self.serial_data[18] << 8) + self.serial_data[19]
            power = (power_par / power_data) * self.vf * self.cf
            print("Active Power:", power, "W")

    
    
    def checksum(self, packet):
        check = 0
        for i in range(2, 23):
            check += packet[i]
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