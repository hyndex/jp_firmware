import pigpio

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

# Turn on the relay (Assuming the relay is active HIGH)
pi.write(relay_pin, 0)


print("Relay on GPIO 18 is turned ON.")

# Clean up
pi.stop()
