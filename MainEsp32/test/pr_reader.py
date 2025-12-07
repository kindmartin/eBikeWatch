
# ================================
# 4) pr_reader.py
# ================================

import uasyncio as asyncio, machine
import HW

try:
    from .phaserunner import Phaserunner  # fileciteturn0file2
except Exception as e:
    Phaserunner = None
    print("Phaserunner lib missing:", e)


_pr = None


def setup_uart1():
    u = HW.config["UART1"]
    uart = machine.UART(1, baudrate=u["baud"], tx=machine.Pin(u["tx"]), rx=machine.Pin(u["rx"]), bits=u["bits"], parity=u["parity"], stop=u["stop"])
    return uart


def pr():
    global _pr
    if _pr: return _pr
    if Phaserunner is None:
        return None
    _pr = Phaserunner(setup_uart1(), slave_id=1)
    return _pr


async def task_pr_poll(period_ms=200):
    if pr() is None:
        print("PR task disabled (no library)")
        return
    keys = [
        "battery_voltage",
        "battery_current",
        "motor_current",
        "controller_temp",
        "motor_temp",
        "vehicle_speed",
        "throttle_voltage",
        "brake_voltage_1",
    ]
    while True:
        try:
            data = {}
            for k in keys:
                try:
                    data[k] = pr().read_value(k)
                except Exception:
                    data[k] = None
            # Minimal reporting (replace with BLE/UART/Log as needed)
            print("PR:", data)
        except Exception as e:
            print("PR poll error:", e)
        await asyncio.sleep_ms(period_ms)

