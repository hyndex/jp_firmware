import serial
import time

class HLW8032:
    def __init__(self, port, baudrate=4800):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as e:
            print(f"Error opening serial port {port}: {e}")
            self.ser = None

    def read_data(self):
        if self.ser and self.ser.in_waiting >= 24:
            try:
                raw_data = self.ser.read(24)  # Read 24 bytes as per documentation
                self.parse_data(raw_data)
            except serial.SerialException as e:
                print(f"Error reading data from serial port: {e}")

    def parse_data(self, raw_data):
        try:
            # Parse the raw data into meaningful values
            # Assuming the data is in big-endian format
            self.data['state_reg'] = raw_data[0]
            self.data['check_reg'] = raw_data[1]
            self.data['voltage_parameter_reg'] = int.from_bytes(raw_data[2:5], byteorder='big')
            self.data['voltage_reg'] = int.from_bytes(raw_data[5:8], byteorder='big')
            self.data['current_parameter_reg'] = int.from_bytes(raw_data[8:11], byteorder='big')
            self.data['current_reg'] = int.from_bytes(raw_data[11:14], byteorder='big')
            self.data['power_parameter_reg'] = int.from_bytes(raw_data[14:17], byteorder='big')
            self.data['power_reg'] = int.from_bytes(raw_data[17:20], byteorder='big')
            self.data['data_update_reg'] = raw_data[20]
            self.data['pf_reg'] = int.from_bytes(raw_data[21:23], byteorder='big')
            self.data['checksum_reg'] = raw_data[23]
        except Exception as e:
            print(f"Error parsing data: {e}")

    def get_data(self):
        return self.data

    def close(self):
        if self.ser:
            self.ser.close()



# Usage example
if __name__ == '__main__':
    hlw8032 = HLW8032('/dev/ttyUSB0')  # Adjust the serial port as needed
    try:
        while True:
            hlw8032.read_data()
            data = hlw8032.get_data()
            if data:
                print("Voltage:", data.get('voltage_reg'))
                print("Current:", data.get('current_reg'))
                print("Power:", data.get('power_reg'))
            time.sleep(3)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        hlw8032.close()







