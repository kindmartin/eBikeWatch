"""Minimal Phaserunner link smoke-test for the PR-offload ESP32.

Usage (MicroPython REPL on the offload board):
    import test.pr_link_smoke as smoke
    smoke.run(duration_s=30, pause_ms=250)

It uses the pin definitions from HW.py, opens the Modbus UART, and polls a
small register set so you can verify RX/TX wiring, baud rate, and overall link
health without running the full offload firmware.
"""

import time
import machine

from HW import PR_UART_ID, PR_UART_TX, PR_UART_RX, PR_UART_BAUD
from phaserunner import Phaserunner

READ_REGS = (
    "battery_voltage",
    "battery_current",
    "motor_input_power",
    "vehicle_speed",
    "controller_temp",
    "motor_temp",
    "motor_rpm",
)


def _open_uart():
    # HW constants are named from the Phaserunner point of view (PR_UART_TX is the
    # line driven by the PR). From the ESP32 perspective we must cross them: our
    # TX pin has to drive the PR's RX line, so we hook PR_UART_RX for TX and
    # PR_UART_TX for RX, exactly like the production bridge does.
    return machine.UART(
        PR_UART_ID,
        baudrate=PR_UART_BAUD,
        tx=machine.Pin(PR_UART_RX),
        rx=machine.Pin(PR_UART_TX),
        timeout=200,
        timeout_char=2,
    )


def run(duration_s=20, pause_ms=250):
    """Poll a handful of Phaserunner registers for ``duration_s`` seconds."""

    try:
        uart = _open_uart()
    except Exception as exc:  # pragma: no cover - hardware only
        print("[smoke] unable to open PR UART:", exc)
        return False

    pr = Phaserunner(uart)
    ok = 0
    errors = 0
    deadline = time.ticks_add(time.ticks_ms(), int(duration_s * 1000))

    print(
        "[smoke] starting PR probe for {}s (pause {} ms, regs={})".format(
            duration_s, pause_ms, len(READ_REGS)
        )
    )

    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            for name in READ_REGS:
                try:
                    value = pr.read_value(name)
                    ok += 1
                    print("{:>18}: {:.3f}".format(name, value))
                except Exception as exc:
                    errors += 1
                    print("{:>18}: ERROR {}".format(name, exc))
                time.sleep_ms(pause_ms)
    finally:
        try:
            uart.deinit()
        except Exception:
            pass

    print(
        "[smoke] done -> ok={} errors={} success_rate={:.1f}%".format(
            ok,
            errors,
            100.0 * ok / (ok + errors) if (ok + errors) else 0.0,
        )
    )
    return errors == 0


run()
