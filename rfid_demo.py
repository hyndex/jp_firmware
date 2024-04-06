from MFRC522 import SimpleMFRC522
import time

def continuous_read():
    reader = SimpleMFRC522()
    
    try:
        print("Place your RFID tag near the reader...")
        while True:
            id, text = reader.read_no_block()
            if id:  # If an ID is found
                print(f"ID: {id}")
                if text:
                    print(f"Text: {text}")
                else:
                    print("No text found on the tag.")
                
                # Brief pause to prevent immediate re-reads
                time.sleep(1)
                
            else:
                # Optional: You can sleep for a shorter time if you want quicker rechecks without a tag present
                time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("Stopping RFID read loop.")
        # No need to clean up GPIO since pigpio handles this in the background

if __name__ == "__main__":
    continuous_read()
