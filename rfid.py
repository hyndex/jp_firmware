import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import json
import time

# Create an object of the class MFRC522
reader = SimpleMFRC522()

RFID_FILE_PATH = "/dev/shm/rfid.json"
RFID_EXPIRY_TIME = 5  # in seconds

def write_to_file(data):
    with open(RFID_FILE_PATH, "w") as file:
        json.dump(data, file)

def read_from_file():
    try:
        with open(RFID_FILE_PATH, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return None

def clear_file():
    with open(RFID_FILE_PATH, "w") as file:
        file.write("")

try:
    last_write_time = 0
    last_data = None

    # Create the RFID file if it doesn't exist
    open(RFID_FILE_PATH, "a").close()

    while True:
        print("Hold a tag near the reader")
        # This will run indefinitely, waiting for a tag to be close enough to the reader
        id, text = reader.read()  # When a tag is read, the id and text from it are returned
        print(f"ID: {id}")
        print(f"Text: {text}")

        # Replace invalid text with an empty string
        if not text or "\x00" in text:
            text = ""

        current_time = time.time()

        # Check if the data is different from the last one and the time has expired
        if (text != last_data or id != last_data['id'] or current_time - last_write_time >= RFID_EXPIRY_TIME):
            # Write the RFID data to /dev/shm/rfid.json
            write_to_file({"id": id, "text": text})
            last_write_time = current_time
            last_data = {"id": id, "text": text}

except KeyboardInterrupt:
    # If the user presses CTRL+C, cleanup and stop
    print("Exiting...")
    GPIO.cleanup()
