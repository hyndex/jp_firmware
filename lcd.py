import board
import digitalio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import time

# Create the I2C interface.
i2c = board.I2C()

# Create the SSD1306 OLED class.
display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

# Clear the display.
display.fill(0)
display.show()

# Create a blank image for drawing.
image = Image.new("1", (display.width, display.height))

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)

# Define the default font.
font = ImageFont.load_default()

# Function to show a message on the display
def show_message(lines, spacing=8):
    draw.rectangle((0, 0, display.width, display.height), outline=0, fill=0)
    for i, line in enumerate(lines):
        draw.text((0, i * spacing), line, font=font, fill=255)
    display.image(image)
    display.show()

# Display "1:A | 2:C | 3:F"
show_message(["1:A | 2:C | 3:F"])
time.sleep(5)  # Show the message for 5 seconds

# Display "Welcome to Joulepoint"
show_message(["Welcome to Joulepoint"])
time.sleep(5)  # Show the message for 5 seconds

# Display energy values
energy_messages = [
    "1: Energy 200 Wh",
    "2: Energy 1000 Wh",
    "3: Energy N/A"
]
show_message(energy_messages, spacing=10)
# No sleep here to keep the last message displayed

