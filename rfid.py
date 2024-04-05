import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import json

# Create an object of the class MFRC522
reader = SimpleMFRC522()

def write_to_file(data):
    with open("/dev/shm/rfid.json", "w") as file:
        json.dump(data, file)

try:
    while True:
        print("Hold a tag near the reader")
        # This will run indefinitely, waiting for a tag to be close enough to the reader
        id, text = reader.read()  # When a tag is read, the id and text from it are returned
        print(f"ID: {id}")
        print(f"Text: {text}")
        
        # Write the RFID data to /dev/shm/rfid.json
        write_to_file({"id": id, "text": text})
except KeyboardInterrupt:
    # If the user presses CTRL+C, cleanup and stop
    print("Exiting...")
    GPIO.cleanup()
