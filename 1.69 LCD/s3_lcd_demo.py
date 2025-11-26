"""Quick test script for the 1.69" ST7789 LCD using lcd1p69.LCD1p69 on ESP32-S3.

Adjust the pin numbers to match your wiring. Tested on MicroPython v1.27.
"""

from machine import Pin, SPI
from lcd1p69 import LCD1p69, rgb565

# GPIO assignments (update if your wiring differs)
MOSI_PIN = 9   # DIN
MISO_PIN = 10  # Dummy pin so MicroPython does not grab USB D-/D+
SCK_PIN = 8    # CLK
CS_PIN = 7
DC_PIN = 6
RST_PIN = 5
BL_PIN = 4

SPI_ID = 2
SPI_BAUDRATE = 20_000_000


def main() -> None:
    spi = SPI(
        SPI_ID,
        baudrate=SPI_BAUDRATE,
        polarity=0,
        phase=0,
        sck=Pin(SCK_PIN),
        mosi=Pin(MOSI_PIN),
        miso=Pin(MISO_PIN),
    )

    lcd = LCD1p69(
        spi,
        dc=Pin(DC_PIN, Pin.OUT),
        rst=Pin(RST_PIN, Pin.OUT),
        cs=Pin(CS_PIN, Pin.OUT),
        bl=Pin(BL_PIN, Pin.OUT),
        rotation=0,
    )

    lcd.fill(rgb565(0, 0, 32))
    lcd.text("ESP32-S3", 40, 40, rgb565(255, 255, 0))
    lcd.text("ST7789 1.69\"", 30, 70, rgb565(0, 255, 0))
    lcd.text("Hola!", 90, 110, rgb565(255, 0, 0))
    lcd.show()


main()
