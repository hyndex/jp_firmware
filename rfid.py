# import RPi.GPIO as GPIO
# from mfrc522 import SimpleMFRC522

# # Create an object of the class MFRC522
# reader = SimpleMFRC522()

# try:
#     while True:
#         print("Hold a tag near the reader")
#         # This will run indefinitely, waiting for a tag to be close enough to the reader
#         id, text = reader.read()  # When a tag is read, the id and text from it are returned
#         print(f"ID: {id}")
#         print(f"Text: {text}")
# except KeyboardInterrupt:
#     # If the user presses CTRL+C, cleanup and stop
#     print("Exiting...")
#     GPIO.cleanup()


# rfid.py
# rfid.py
import platform
import os


def is_raspberry_pi():
    return platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model')


# Only import the GPIO library and create the reader if we're on a Raspberry Pi
if platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model'):
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    reader = SimpleMFRC522()
else:
    GPIO = None
    reader = None

def read_rfid():
    # If we're not on a Raspberry Pi, just simulate a read
    if not is_raspberry_pi():
        print("Simulated RFID read (no hardware found)")
        return None, None

    # If we're on a Raspberry Pi, perform the actual read
    try:
        id, text = reader.read()
        print('RFID',id,text)
        return id, text
    except Exception as e:
        print(f"RFID read error: {e}")
        return None, None

def cleanup_rfid():
    if GPIO is not None:
        GPIO.cleanup()


