"""Manual UART link test for the PR-offload ESP32.

Use this script on the offload MCU to exercise the UART bridge that connects to
the main ESP32 controller. Import from the REPL and use `send_line(...)` plus
`read_available()` to verify traffic in each direction, or start `ping_loop()`
for an automated keeps-alive stream.
Wiring (ESP32 to ESP32):
- Main ESP32 RX -> ESP32 GPIO 4 (UART TX)
- Main ESP32 TX -> ESP32 GPIO 5 (UART RX)

"""

from machine import UART
from time import sleep_ms, ticks_add, ticks_diff, ticks_ms

from HW import MAIN_UART_BAUD, MAIN_UART_ID, MAIN_UART_RX, MAIN_UART_TX

# Expose the UART instance as `u` for parity with the main-side helper.
u = UART(
    MAIN_UART_ID,
    baudrate=MAIN_UART_BAUD,
    tx=MAIN_UART_TX,
    rx=MAIN_UART_RX,
    timeout=0,
    timeout_char=5,
)


def send_line(text, *, append_newline=True):
    """Send bytes toward the main ESP32 controller."""

    if isinstance(text, str):
        payload = text.encode()
    else:
        payload = bytes(text)
    if append_newline and not payload.endswith(b"\n"):
        payload += b"\n"
    u.write(payload)


def read_available():
    """Print any characters received from the main controller."""

    data = u.read()
    if data:
        try:
            decoded = data.decode().rstrip("\n")
        except Exception:
            decoded = repr(data)
        print("[rx-offload]", decoded)
    return data


def ping_loop(*, label="OFFLOAD", interval_ms=1000, echo=False):
    """Emit periodic pings; optionally echo any received payloads."""

    counter = 0
    next_ping = ticks_add(ticks_ms(), interval_ms)
    try:
        while True:
            data = read_available()
            if echo and data:
                send_line(data, append_newline=False)
            now = ticks_ms()
            if ticks_diff(now, next_ping) >= 0:
                send_line("{} ping {}".format(label, counter))
                counter += 1
                next_ping = ticks_add(now, interval_ms)
            sleep_ms(20)
    except KeyboardInterrupt:
        print("[ping-loop] stopped")


def close_uart():
    """Release the UART peripheral when done testing."""

    u.deinit()
