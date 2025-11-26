"""
PR-offload ESP32 firmware: polls Phaserunner via UART and relays data to main ESP32.

Connections:
- PR TX -> ESP32 GPIO 25 (UART RX)
- PR RX -> ESP32 GPIO 26 (UART TX)
- Main ESP32 RX -> ESP32 GPIO 19 (UART TX)
- Main ESP32 TX -> ESP32 GPIO 18 (UART RX)

This script polls PR registers and sends results as JSON lines over the main ESP32 UART.
"""

import json
import time

import _thread
import machine

from HW import PR_UART_RX, PR_UART_TX
from phaserunner import Phaserunner


# PR UART (to Phaserunner)
PR_UART_ID = 1
PR_BAUD = 115200

# Main ESP32 UART (for relay)
MAIN_UART_ID = 2
MAIN_UART_TX = 19
MAIN_UART_RX = 18
MAIN_BAUD = 115200

FAST_INTERVAL_MS_DEFAULT = 50   # 20 Hz
SLOW_INTERVAL_MS_DEFAULT = 1000  # 1 Hz

_fast_interval_ms = FAST_INTERVAL_MS_DEFAULT
_slow_interval_ms = SLOW_INTERVAL_MS_DEFAULT
_latest_fast = {}
_latest_slow = {}
_latest_errors = {}
_last_payload_ts = 0
_last_seq = 0
_worker_thread = None
_stop_requested = False

FAST_REGS = ["battery_current", "vehicle_speed", "motor_input_power"]
SLOW_REGS = [
    "controller_temp",
    "motor_temp",
    "motor_rpm",
    "battery_voltage",
    "throttle_voltage",
    "brake_voltage_1",
    "digital_inputs",
    "warnings",
]


def _safe_read(pr, name, state):
    entry = state.setdefault(name, {"value": None, "errors": 0, "last_error": None})
    try:
        value = pr.read_value(name)
        entry["value"] = value
        entry["last_error"] = None
        return value
    except Exception as exc:
        entry["errors"] += 1
        entry["last_error"] = repr(exc)
        return None


def _worker_loop():
    global _worker_thread, _latest_fast, _latest_slow, _latest_errors, _last_payload_ts, _last_seq

    pr_uart = None
    main_uart = None
    try:
        # HW constants are defined from the Phaserunner perspective (PR_UART_TX is the line driven by the PR).
        # From the ESP32 perspective we need to cross them: TX pin drives the PR's RX line, so use PR_UART_RX.
        pr_uart = machine.UART(
            PR_UART_ID,
            baudrate=PR_BAUD,
            tx=machine.Pin(PR_UART_RX),
            rx=machine.Pin(PR_UART_TX),
            timeout=300,
        )
        main_uart = machine.UART(
            MAIN_UART_ID,
            baudrate=MAIN_BAUD,
            tx=machine.Pin(MAIN_UART_TX),
            rx=machine.Pin(MAIN_UART_RX),
            timeout=100,
        )
        pr = Phaserunner(pr_uart)

        cache = {}
        seq = 0
        slow_snapshot = {}
        next_slow = time.ticks_add(time.ticks_ms(), _slow_interval_ms)
        slow_interval_last = _slow_interval_ms

        while not _stop_requested:
            current_fast_ms = _fast_interval_ms
            current_slow_ms = _slow_interval_ms
            payload = {
                "ts": time.ticks_ms(),
                "seq": seq,
                "fast": {},
                "slow": slow_snapshot,
                "errors": {},
            }

            for reg in FAST_REGS:
                value = _safe_read(pr, reg, cache)
                payload["fast"][reg] = value
                if cache[reg]["last_error"]:
                    payload["errors"][reg] = cache[reg]["last_error"]

            now = time.ticks_ms()
            if time.ticks_diff(now, next_slow) >= 0 or current_slow_ms != slow_interval_last:
                slow_snapshot = {}
                for reg in SLOW_REGS:
                    value = _safe_read(pr, reg, cache)
                    slow_snapshot[reg] = value
                    if cache[reg]["last_error"]:
                        payload["errors"][reg] = cache[reg]["last_error"]
                payload["slow"] = slow_snapshot
                next_slow = time.ticks_add(now, current_slow_ms)
                slow_interval_last = current_slow_ms

            try:
                main_uart.write(json.dumps(payload) + "\n")
            except Exception:
                pass

            _latest_fast = payload["fast"].copy()
            _latest_slow = payload["slow"].copy()
            _latest_errors = payload["errors"].copy()
            _last_payload_ts = payload["ts"]
            _last_seq = seq

            seq = (seq + 1) & 0xFFFF
            time.sleep_ms(current_fast_ms)
    except Exception as exc:
        print("PR-offload error:", exc)
    finally:
        if pr_uart:
            pr_uart.deinit()
        if main_uart:
            main_uart.deinit()
        _worker_thread = None


def start():
    """Start the PR-offload worker in a background thread if not already running."""
    global _worker_thread, _stop_requested
    if _worker_thread is not None:
        return False
    _stop_requested = False
    _worker_thread = _thread.start_new_thread(_worker_loop, ())
    return True


def stop(wait_ms=0):
    """Signal the worker to stop and optionally wait for completion."""
    global _stop_requested
    _stop_requested = True
    waited = 0
    while _worker_thread is not None and waited < wait_ms:
        time.sleep_ms(10)
        waited += 10
    return _worker_thread is None


def is_running():
    return _worker_thread is not None


def run():
    """Legacy entry point; start background worker."""
    start()


# Auto-start on import so the poller runs regardless of entrypoint
start()


# ---------------------------------------------------------------------------
# REPL helper functions (import pr_offload_esp32 as off)
# ---------------------------------------------------------------------------

def get_fast_interval():
    """Return the current fast-loop interval in ms."""
    return _fast_interval_ms


def set_fast_interval(ms):
    """Update the fast-loop interval (ms). Minimum 20 ms."""
    global _fast_interval_ms
    ms = max(20, int(ms))
    _fast_interval_ms = ms
    return _fast_interval_ms


def get_slow_interval():
    """Return the current slow-loop interval in ms."""
    return _slow_interval_ms


def set_slow_interval(ms):
    """Update the slow-loop interval (ms). Minimum equals fast interval."""
    global _slow_interval_ms
    ms = max(_fast_interval_ms, int(ms))
    _slow_interval_ms = ms
    return _slow_interval_ms


def get_latest(name):
    """Return the most recent value for a register (fast or slow)."""
    if name in _latest_fast:
        return _latest_fast.get(name)
    return _latest_slow.get(name)


def get_snapshot():
    """Return a copy of the latest payload (fast, slow, errors, timestamps)."""
    return {
        "ts": _last_payload_ts,
        "seq": _last_seq,
        "fast": _latest_fast.copy(),
        "slow": _latest_slow.copy(),
        "errors": _latest_errors.copy(),
    }


def get_errors():
    """Return the current error map."""
    return _latest_errors.copy()
