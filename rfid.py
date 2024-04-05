# # rfid.py
# import platform
# import os


# def is_raspberry_pi():
#     return platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model')


# # Only import the GPIO library and create the reader if we're on a Raspberry Pi
# if platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model'):
#     import RPi.GPIO as GPIO
#     from mfrc522 import SimpleMFRC522
#     reader = SimpleMFRC522()
# else:
#     GPIO = None
#     reader = None

# def read_rfid():
#     # If we're not on a Raspberry Pi, just simulate a read
#     if not is_raspberry_pi():
#         print("Simulated RFID read (no hardware found)")
#         return None, None

#     # If we're on a Raspberry Pi, perform the actual read
#     try:
#         id, text = reader.read()
#         print('RFID',id,text)
#         return id, text
#     except Exception as e:
#         print(f"RFID read error: {e}")
#         return None, None

# def cleanup_rfid():
#     if GPIO is not None:
#         GPIO.cleanup()





import platform
import os
import asyncio

# Check if running on Raspberry Pi
def is_raspberry_pi():
    return platform.system() == 'Linux' and os.path.exists('/proc/device-tree/model')

if is_raspberry_pi():
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    reader = SimpleMFRC522()
else:
    GPIO = None
    reader = None

async def read_rfid():
    # Wrap blocking RFID read call in asyncio.to_thread to run it in a separate thread
    if not is_raspberry_pi():
        print("Simulated RFID read (no hardware found)")
        return None, None

    try:
        # Use to_thread to make the blocking call to reader.read non-blocking
        id, text = await asyncio.to_thread(reader.read)
        print('RFID', id, text)
        return id, text
    except Exception as e:
        print(f"RFID read error: {e}")
        if GPIO is not None:
            GPIO.cleanup()  # Cleanup GPIO resources on error
        raise  # Re-raise the exception after cleanup

def cleanup_rfid():
    # This function can be used for explicit cleanup when no exceptions occur
    if GPIO is not None:
        GPIO.cleanup()
