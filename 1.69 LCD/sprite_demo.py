"""Draw a converted sprite module (pic_sprite.py) on the 1.69" LCD."""

from machine import Pin, SPI
from lcd1p69 import LCD1p69

try:
    from pic_sprite import WIDTH, HEIGHT, DATA
except ImportError:
    raise SystemExit("Upload pic_sprite.py (from convert_assets.py sprite) to the board first")

MOSI_PIN = 9
MISO_PIN = 10
SCK_PIN = 8
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

    x = (lcd.width - WIDTH) // 2
    y = (lcd.height - HEIGHT) // 2
    lcd.fill(0)
    lcd.blit_buffer(DATA, x, y, WIDTH, HEIGHT)
    lcd.show()


main()
