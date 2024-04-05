import board
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import time

# Initialize I2C. This automatically selects the correct I2C bus and pins for the Raspberry Pi.
i2c = board.I2C()

# Create an instance of the SSD1306 OLED display class.
# Specify the display dimensions (width and height) during initialization.
display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

# Clear the display to ensure it starts with a blank canvas.
display.fill(0)
display.show()

# Create a blank image for drawing. Ensure the image has the same dimensions as the display.
image = Image.new('1', (display.width, display.height))

# Prepare a drawing context to draw on the image.
draw = ImageDraw.Draw(image)

# Load the default font to use for text.
font = ImageFont.load_default()

def show_message(lines, spacing=8):
    """
    Display a list of lines on the OLED screen, with a specified spacing between lines.
    
    :param lines: A list of strings, each representing a line of text to be displayed.
    :param spacing: The vertical spacing between lines of text.
    """
    # Clear the image before drawing the new content.
    draw.rectangle((0, 0, display.width, display.height), outline=0, fill=0)
    
    # Iterate over the lines of text, drawing each one.
    for i, line in enumerate(lines):
        draw.text((0, i * spacing), line, font=font, fill=255)
    
    # Update the display with the new image.
    display.image(image)
    display.show()

# Display various messages with a delay between each.
show_message(["1:A | 2:C | 3:F"])
time.sleep(5)  # Display this message for 5 seconds.

show_message(["Welcome to Joulepoint"])
time.sleep(5)  # Display this message for 5 seconds.

# Display multiple lines of energy values.
energy_messages = [
    "1: Energy 200 Wh",
    "2: Energy 1000 Wh",
    "3: Energy N/A"
]
show_message(energy_messages, spacing=10)  # Increase spacing due to potentially longer lines.
# The last message stays displayed without a subsequent sleep call.
