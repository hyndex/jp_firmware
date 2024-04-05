# 20_4_lcd_display.py
import platform
import os
if platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model'):
    from RPLCD.i2c import CharLCD
    # Initialize the LCD (change the expander and address if needed)
    lcd = CharLCD('PCF8574', 0x27, port=1, cols=20, rows=4, charmap='A02', dotsize=8)
else:
    lcd = {}

def is_raspberry_pi():
    if platform.system() == 'Linux':
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model_info = file.read()
            return 'Raspberry Pi' in model_info
        except FileNotFoundError:
            return False
    return False

def update_lcd_line(line_number, message, cols=20):


    if(not is_raspberry_pi()):
        print('################',line_number, message)
        return
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

