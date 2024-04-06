from MFRC522 import SimpleMFRC522  # Assuming SimpleMFRC522 is the module name
import json
import time

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

    reader = SimpleMFRC522()  # Create an object of the class MFRC522

    while True:
        print("Hold a tag near the reader")
        id, text = reader.read()  # This will run indefinitely, waiting for a tag
        print(f"ID: {id}")
        print(f"Text: {text}")

        # Replace invalid text with an empty string
        if not text or "\x00" in text:
            text = ""

        current_time = time.time()

        # Check if the data is different from the last one or the time has expired
        if text != last_data or (last_data and id != last_data['id']) or current_time - last_write_time >= RFID_EXPIRY_TIME:
            # Write the RFID data to /dev/shm/rfid.json
            write_to_file({"id": id, "text": text})
            last_write_time = current_time
            last_data = {"id": id, "text": text}

except KeyboardInterrupt:
    # If the user presses CTRL+C, print exiting message
    print("Exiting...")
    # No GPIO.cleanup() needed here as pigpio cleanup is handled internally
