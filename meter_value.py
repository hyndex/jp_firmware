import time

class MeterReadingCorrector:
    def __init__(self, max_valid_voltage, max_valid_current, max_power_rate_increase):
        self.max_valid_voltage = max_valid_voltage
        self.max_valid_current = max_valid_current
        self.max_power_rate_increase = max_power_rate_increase  # Max power increase per second
        self.last_valid_power = 0
        self.last_valid_time = time.time()

    def add_and_correct_readings(self, voltage, current, power):
        """Add new readings and correct if necessary."""
        corrected_voltage = min(voltage, self.max_valid_voltage)
        corrected_current = min(current, self.max_valid_current)
        corrected_power = self.correct_power(power, corrected_voltage, corrected_current)

        return corrected_voltage, corrected_current, corrected_power

    def correct_power(self, power, voltage, current):
        """Correct power reading based on voltage and current."""
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

# Example usage
meter_reading_corrector = MeterReadingCorrector(
    max_valid_voltage=240, max_valid_current=30, max_power_rate_increase=100  # 100 Wh per second
)

# Simulated readings
readings = [
    (230, 15, 3500),  # Normal
    (245, 16, 3600),  # Voltage slightly higher
    (230, 15, 7000),  # Power too high
    (250, 31, 4000),  # Voltage and current too high
    # Add more readings as needed
]

for voltage, current, power in readings:
    corrected_voltage, corrected_current, corrected_power = meter_reading_corrector.add_and_correct_readings(
        voltage, current, power
    )
    print(f"Corrected Readings: Voltage={corrected_voltage}, Current={corrected_current}, Power={corrected_power}")
