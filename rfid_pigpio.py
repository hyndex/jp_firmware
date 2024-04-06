import pigpio
import time

class MFRC522:
    def __init__(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise IOError("Cannot connect to pigpio daemon")
        
        self.spi_channel = 0
        self.spi_speed = 1000000  # 1 MHz
        self.spi_flags = 0
        
        self.spi_handle = self.pi.spi_open(self.spi_channel, self.spi_speed, self.spi_flags)
        
        self.reset()

    def reset(self):
        self.write_register(0x01, 0x0F)

    def write_register(self, reg, val):
        addr = (reg << 1) & 0x7E
        self.pi.spi_write(self.spi_handle, [addr, val])

    def read_register(self, reg):
        addr = ((reg << 1) & 0x7E) | 0x80
        _, data = self.pi.spi_xfer(self.spi_handle, [addr, 0])
        return data[1]

    def detect_card(self):
        # Put the reader in the idle state
        self.write_register(0x01, 0x00)
        
        # Transmit the request command
        self.write_register(0x0D, 0x07)  # Set the bit framing for the request
        self.write_register(0x04, 0x26)  # Request command for Type A
        self.write_register(0x02, 0x07)  # Enable IRQ on detect
        self.write_register(0x01, 0x0C)  # Transceive command
        
        time.sleep(0.01)  # Wait for card to respond
        
        irq = self.read_register(0x04)  # Check IRQ register
        if irq & 0x30:  # If we see a response
            return True
        return False

    def get_card_serial(self):
        # Anticollision command sequence to get the UID
        self.write_register(0x02, 0x93)  # Level for anticollision
        self.write_register(0x0D, 0x20)  # Send anticollision command
        self.write_register(0x01, 0x0C)  # Transceive the data
        
        time.sleep(0.01)
        
        uid = []
        for i in range(0x09, 0x0D):  # Read block that should contain the UID
            uid.append(self.read_register(i))
        
        return uid

    def close(self):
        self.pi.spi_close(self.spi_handle)
        self.pi.stop()

if __name__ == "__main__":
    try:
        rfid = MFRC522()
        print("Place card near reader")
        while True:
            if rfid.detect_card():
                uid = rfid.get_card_serial()
                print(f"Card detected: UID {uid}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("Program exited")
    finally:
        rfid.close()
