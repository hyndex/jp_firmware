import smbus
import time

# Create an instance of the I2C bus
bus = smbus.SMBus(1)

# RFID reader I2C address (you need to replace this with the address you find using i2cdetect)
ADDRESS = 0xXX

def read_rfid():
    try:
        # Your RFID reader's documentation will provide specifics on which bytes to read
        data = bus.read_i2c_block_data(ADDRESS, 0, 16)  # replace '0' with the correct register if needed
        return data
    except Exception as e:
        print(f"Error reading from RFID reader: {e}")

# Main loop to continuously read the RFID tag
try:
    while True:
        card_data = read_rfid()
        print(card_data)
        time.sleep(1)  # pause for 1 second before the next read
except KeyboardInterrupt:
    print("Program terminated by user")
