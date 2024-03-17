import pigpio
import sys

# Initialize the pigpio library
pi = pigpio.pi()

# Check if the pigpio daemon is running
if not pi.connected:
    print("pigpio daemon is not running. Please start it with 'sudo pigpiod'.")
    exit()

# Define the GPIO pin for the relay
relay_pin = 18

# Set the relay pin as an output
pi.set_mode(relay_pin, pigpio.OUTPUT)

# Check if the script received a command-line argument
if len(sys.argv) != 2:
    print("Usage: python relay.py [0/1]")
    exit()

# Turn the relay on or off based on the command-line argument
if sys.argv[1] == '1':
    pi.write(relay_pin, 1)
    print("Relay on GPIO 18 is turned ON.")
elif sys.argv[1] == '0':
    pi.write(relay_pin, 0)
    print("Relay on GPIO 18 is turned OFF.")
else:
    print("Invalid argument. Please use 0 to turn off the relay or 1 to turn it on.")

# Clean up
pi.stop()
