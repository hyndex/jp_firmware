import RPi.GPIO as GPIO
import sys

# Set the GPIO numbering mode
GPIO.setmode(GPIO.BCM)

# Check if the script received the correct number of command-line arguments
if len(sys.argv) != 3:
    print("Usage: python relay.py [GPIO_PIN] [0/1]")
    exit()

# Parse the GPIO pin number and relay state from the command-line arguments
relay_pin = int(sys.argv[1])
relay_state = sys.argv[2]

# Set the relay pin as an output
GPIO.setup(relay_pin, GPIO.OUT)

# Turn the relay on or off based on the command-line argument
if relay_state == '1':
    GPIO.output(relay_pin, GPIO.HIGH)
    print(f"Relay on GPIO {relay_pin} is turned ON.")
elif relay_state == '0':
    GPIO.output(relay_pin, GPIO.LOW)
    print(f"Relay on GPIO {relay_pin} is turned OFF.")
else:
    print("Invalid argument. Please use 0 to turn off the relay or 1 to turn it on.")

# Clean up
GPIO.cleanup()
