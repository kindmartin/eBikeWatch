"""Manual UART link test for the main ESP32 controller.

This script exposes helpers that make it easy to validate the two-way UART
connection with the PR-offload ESP32. Import the module from the REPL and use
`send_line(...)` to push data while `read_available()` prints anything received.
`ping_loop()` can be used to automate periodic chatter for soak testing.
"""

from machine import UART
from time import sleep_ms, ticks_add, ticks_diff, ticks_ms

from HW import PR_UART_BAUD, PR_UART_ID, PR_UART_RX, PR_UART_TX

# Shared UART handle used by the helper functions below. The object is named `u`
# so it can be inspected directly from the REPL if desired.
u = UART(
    PR_UART_ID,
    baudrate=PR_UART_BAUD,
    tx=PR_UART_TX,
    rx=PR_UART_RX,
    timeout=0,
    timeout_char=5,
)


def send_line(text, *, append_newline=True):
    """Send a line of text to the PR-offload ESP32."""

    if isinstance(text, str):
        payload = text.encode()
    else:
        payload = bytes(text)
    if append_newline and not payload.endswith(b"\n"):
        payload += b"\n"
    u.write(payload)


def read_available():
    """Read and print any pending bytes from the UART buffer."""

    data = u.read()
    if data:
        try:
            decoded = data.decode().rstrip("\n")
        except Exception:
            decoded = repr(data)
        print("[rx-main]", decoded)
    return data


def ping_loop(*, label="MAIN", interval_ms=1000):
    """Send a numbered ping every `interval_ms` while printing RX data."""

    counter = 0
    next_ping = ticks_add(ticks_ms(), interval_ms)
    try:
        while True:
            read_available()
            now = ticks_ms()
            if ticks_diff(now, next_ping) >= 0:
                send_line("{} ping {}".format(label, counter))
                counter += 1
                next_ping = ticks_add(now, interval_ms)
            sleep_ms(20)
    except KeyboardInterrupt:
        print("[ping-loop] stopped")


def close_uart():
    """Release the UART when finished testing."""

    u.deinit()
