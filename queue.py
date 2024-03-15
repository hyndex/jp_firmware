import queue
import time

class HLW8032:
    def __init__(self, pi, rx_pin):
        self.pi = pi
        self.rx_pin = rx_pin
        self.buffer = queue.Queue()
        self.vf = 1880000 / (1000 * 1000.0)  # Calculate voltage coefficient
        self.cf = 1.0 / (0.001 * 1000.0)      # Calculate current coefficient
        self.pi.set_mode(rx_pin, pigpio.INPUT)
        self.pi.bb_serial_read_open(rx_pin, 4800, 9)  # 9 bits (8 data + 1 parity)

    def serial_read_loop(self):
        (count, data) = self.pi.bb_serial_read(self.rx_pin)
        if count > 0:
            for byte in data:
                self.buffer.put(byte)
                if self.buffer.qsize() >= 24:
                    self.process_data()

    def process_data(self):

        hex_data = [hex(byte) for byte in packet]
        a = 0
        if hex_data[2] == '0x5a':
            print('A', packet, len(packet))
            print('B', hex_data)
            a = 1


        packet = [self.buffer.get() for _ in range(24)]
        if packet[2] != 0x5A:
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




        # Parse and print the data, similar to the parse_data method previously discussed

        

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
try:
    while True:
        hlw8032.serial_read_loop()
        time.sleep(0.05)
finally:
    hlw8032.close()
    pi.stop()
