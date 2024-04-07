# 20_4_lcd_display_test.py
import platform
import os

class MockLCD:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.cursor_pos = (0, 0)

    def write_string(self, message):
        print(f"LCD {self.cursor_pos[0] + 1}:{message}")

# Check if running on Raspberry Pi
def is_raspberry_pi():
    if platform.system() == 'Linux':
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

if is_raspberry_pi() and os.path.exists('/proc/device-tree/model'):
    from RPLCD.i2c import CharLCD
    lcd = CharLCD('PCF8574', 0x27, port=1, cols=20, rows=4, charmap='A02', dotsize=8)
else:
    # Use a mock LCD for non-Raspberry Pi environments
    lcd = MockLCD(cols=20, rows=4)

def update_lcd_line(line_number, message, cols=20):
    """
    Update a single line of the LCD with the provided message.
    :param line_number: Line number to update (1-4).
    :param message: Message to display on the line.
    :param cols: Number of columns the LCD has.
    """
    if 1 <= line_number <= 4:
        # Move cursor to the beginning of the specified line (line numbers start from 1)
        lcd.cursor_pos = (line_number - 1, 0)
        # Clear the line before updating
        lcd.write_string(' ' * cols)
        # Move cursor back to the beginning of the specified line
        lcd.cursor_pos = (line_number - 1, 0)
        # Write the new message on the specified line
        lcd.write_string(message[:cols])

def test_lcd_display():
    """
    Test function to write messages on each line of the LCD.
    """
    for i in range(1, 5):  # Assuming 4 lines are available
        update_lcd_line(i, f"Test Line {i}", cols=20)

if __name__ == "__main__":
    test_lcd_display()
