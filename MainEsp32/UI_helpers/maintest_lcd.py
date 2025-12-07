"""Simplified LCD diagnostic demo using the project DisplayUI."""

import uasyncio as asyncio
from time import ticks_ms

from fonts.big_digits import draw_digit
from UI_helpers.ui_display import DisplayUI


async def _animate(ui: DisplayUI):
    speed = 0
    power = 0
    while True:
        ui.d.fill(0)
        ui.d.text("LCD diagnostic", 10, 10, 1)
        ui.d.text("tick:{}".format(ticks_ms() // 1000), 10, 32, 1)
        for i, ch in enumerate(f"{speed:02d}"):
            draw_digit(ui.d, ch, 40 + i * 20, 72)
        ui.d.text("km/h", 100, 88, 1)
        ui.d.text("Power {:4d}W".format(power), 10, 150, 1)
        ui.d.text("Hold Page: cycle", 10, 210, 1)
        ui.d.text("Up/Down: hold", 10, 230, 1)
        ui.d.show()

        speed = (speed + 1) % 100
        power = (power + 25) % 2500
        await asyncio.sleep_ms(120)


def main():
    ui = DisplayUI()
    ui.draw_boot("ST7789 test")
    asyncio.run(_animate(ui))


main()
