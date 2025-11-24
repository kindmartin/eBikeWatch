"""Display converted RGB565 images on the 1.69" LCD.

Copy the generated .bin file from tools/convert_assets.py to the board first.
"""

from machine import Pin, SPI
from lcd1p69 import LCD1p69

MOSI_PIN = 9
MISO_PIN = 10
SCK_PIN = 8
CS_PIN = 7
DC_PIN = 6
RST_PIN = 5
BL_PIN = 4

SPI_ID = 2
SPI_BAUDRATE = 20_000_000
IMAGE_PATH = "pic_demo.bin"


def read_rgb565(path: str) -> bytes:
    with open(path, "rb") as file:
        return file.read()


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

    data = read_rgb565(IMAGE_PATH)
    expected = lcd.width * lcd.height * 2
    if len(data) != expected:
        raise ValueError(
            "image size mismatch: expected %d bytes, got %d" % (expected, len(data))
        )
    lcd.write_rect(0, 0, lcd.width, lcd.height, data)


main()
