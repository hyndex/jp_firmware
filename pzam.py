import serial
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import time

class PowerMeter:
    def __init__(self, port='/dev/ttyS0', baudrate=9600, timeout=2.0, max_valid_voltage=270, max_valid_current=40, max_power_rate_increase=100):
        self.max_valid_voltage = max_valid_voltage
        self.max_valid_current = max_valid_current
        self.max_power_rate_increase = max_power_rate_increase  # Max power increase per second
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.last_valid_power = 0
        self.last_valid_time = time.time()
        self.readings = []  # Store the last 100 readings
        self.latest_corrected_values = {'voltage': 0, 'current': 0, 'power': 0}  # Latest corrected meter values

    def add_and_correct_readings(self, voltage, current, power):
        corrected_voltage = min(voltage, self.max_valid_voltage)
        corrected_current = min(current, self.max_valid_current)
        corrected_power = self.correct_power(power, corrected_voltage, corrected_current)
        return corrected_voltage, corrected_current, corrected_power

    def correct_power(self, power, voltage, current):
        current_time = time.time()
        time_elapsed = current_time - self.last_valid_time
        max_power = self.last_valid_power + time_elapsed * self.max_power_rate_increase
        if power <= max_power:
            self.last_valid_power = power
            self.last_valid_time = current_time
            return power
        estimated_power = voltage * current
        corrected_power = min(max_power, estimated_power)
        self.last_valid_power = corrected_power
        self.last_valid_time = current_time
        return corrected_power

    def read_pzem004t_v3_data(self, change_alarm=False, alarm_value=100, read_interval=5):
        try:
            ser = serial.Serial(port=self.port, baudrate=self.baudrate, bytesize=8, parity='N', stopbits=1, xonxoff=0)
            master = modbus_rtu.RtuMaster(ser)
            master.set_timeout(self.timeout)
            master.set_verbose(True)

            if change_alarm:
                master.execute(1, cst.WRITE_SINGLE_REGISTER, 1, output_value=alarm_value)

            data = master.execute(1, cst.READ_INPUT_REGISTERS, 0, 10)
            voltage = data[0] / 10.0  # [V]
            current = (data[1] + (data[2] << 16)) / 1000.0  # [A]
            power = (data[3] + (data[4] << 16)) / 10.0  # [W]
            voltage, current, power = self.add_and_correct_readings(voltage, current, power)

            self.latest_corrected_values = {'voltage': voltage, 'current': current, 'power': power}  # Update the latest corrected values

            self.store_readings(voltage, current, power)

            print('Latest Corrected Readings: Voltage [V]\t: ', voltage)
            print('Latest Corrected Readings: Current [A]\t: ', current)
            print('Latest Corrected Readings: Power [W]\t: ', power)
            print("--------------------")

            return {'voltage': voltage, 'current': current, 'power': power}


        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            try:
                master.close()
                if ser.is_open:
                    ser.close()
            except:
                pass

    def read_simple_data(self, change_alarm=False, alarm_value=100, read_interval=5):
        try:
            ser = serial.Serial(port=self.port, baudrate=self.baudrate, bytesize=8, parity='N', stopbits=1, xonxoff=0)
            master = modbus_rtu.RtuMaster(ser)
            master.set_timeout(self.timeout)
            master.set_verbose(True)

            if change_alarm:
                master.execute(1, cst.WRITE_SINGLE_REGISTER, 1, output_value=alarm_value)

            data = master.execute(1, cst.READ_INPUT_REGISTERS, 0, 10)
            voltage = data[0] / 10.0  # [V]
            current = (data[1] + (data[2] << 16)) / 1000.0  # [A]
            power = (data[3] + (data[4] << 16)) / 10.0  # [W]

            self.latest_corrected_values = {'voltage': voltage, 'current': current, 'power': power}  # Update the latest corrected values


            print('Latest Readings: Voltage [V]\t: ', voltage)
            print('Latest Readings: Current [A]\t: ', current)
            print('Latest Readings: Power [W]\t: ', power)
            print("--------------------")

            return {'voltage': voltage, 'current': current, 'power': power}


        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            try:
                master.close()
                if ser.is_open:
                    ser.close()
            except:
                pass


    def store_readings(self, voltage, current, power):
        if len(self.readings) >= 100:
            self.readings.pop(0)  # Remove the oldest reading to maintain size
        self.readings.append((voltage, current, power))

    def get_latest_corrected_values(self):
        """Return the latest corrected meter values."""
        return self.latest_corrected_values


# Example usage
corrector = PowerMeter()
# Start reading and correcting data from PZEM-004T V3 sensor
corrector.read_pzem004t_v3_data(change_alarm=True, alarm_value=100)

# To fetch the latest corrected values at any time
latest_values = corrector.get_latest_corrected_values()
print(latest_values)
