from RPLCD.i2c import CharLCD
import smbus2
import time

# Initialize the LCD (update I2C expander and address as needed)
lcd = CharLCD('PCF8574', 0x27, port=1, cols=20, rows=4, charmap='A02', dotsize=8)

# Clear the LCD
lcd.clear()

# Write a message
lcd.write_string('Welcome to Joulepoint')
time.sleep(15)
lcd.crlf()  # Move to the next line
lcd.write_string('1:A | 2:C | 3:F')
time.sleep(15)
lcd.crlf()
lcd.write_string('1: Energy 200 Wh')
time.sleep(15)
lcd.crlf()
lcd.write_string('2: Energy 1000 Wh')
time.sleep(15)

# To update or change the message, simply clear the LCD and write again.
