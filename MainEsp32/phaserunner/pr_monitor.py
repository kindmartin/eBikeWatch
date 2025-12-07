# pr_monitor.py
import uasyncio as asyncio
from machine import UART, Pin

from .phaserunner import Phaserunner
from .registers import PR_REGISTERS as PR

UART_ID   = 2
UART_TX   = 13
UART_RX   = 15
BAUD      = 115200
TIMEOUT_MS = 600
SLAVE_ID  = 1

WATCH = [
    ("battery_voltage", "V"),
    ("battery_current", "A"),
    ("motor_rpm", "rpm"),
    ("controller_temperature", "C"),
]

async def monitor_task(period_ms=500):
    uart = UART(UART_ID, baudrate=BAUD, tx=Pin(UART_TX), rx=Pin(UART_RX),
                timeout=TIMEOUT_MS, timeout_char=0)
    pr = Phaserunner(uart, slave_id=SLAVE_ID)
    print("[PR] monitor @{} baud, UART={}, tx={}, rx={}, slave={}".format(
        BAUD, UART_ID, UART_TX, UART_RX, SLAVE_ID))
    while True:
        parts = []
        for name, unit in WATCH:
            try:
                val = pr.read_value(name)
                if unit:
                    parts.append("{}: {:.3f}{}".format(name, float(val), unit))
                else:
                    parts.append("{}: {}".format(name, val))
            except Exception as e:
                parts.append("{}: ERR({})".format(name, e))
        print("[PR]", " | ".join(parts))
        await asyncio.sleep_ms(period_ms)
