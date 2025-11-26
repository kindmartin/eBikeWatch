"""
PR-offload ESP32 firmware: polls Phaserunner via UART and relays data to main ESP32.

Connections:
- PR TX -> ESP32 GPIO 25 (UART RX)
- PR RX -> ESP32 GPIO 26 (UART TX)
- Main ESP32 RX -> ESP32 GPIO 4 (UART TX)
- Main ESP32 TX -> ESP32 GPIO 5 (UART RX)

This script polls PR registers and sends results as JSON lines over the main ESP32 UART.
"""

import json
import time

import _thread
import machine
import uasyncio as asyncio

from HW import (
    PR_UART_ID,
    PR_UART_TX,
    PR_UART_RX,
    PR_UART_BAUD,
    MAIN_UART_ID,
    MAIN_UART_TX,
    MAIN_UART_RX,
    MAIN_UART_BAUD,
)
from phaserunner import Phaserunner


FAST_INTERVAL_MS_DEFAULT = 50   # 20 Hz
SLOW_INTERVAL_MS_DEFAULT = 1000  # 1 Hz
FW_VERSION = "2025.11.25.2"  # bump when flashing new builds
PROTOCOL_VERSION = 1

_fast_interval_ms = FAST_INTERVAL_MS_DEFAULT
_slow_interval_ms = SLOW_INTERVAL_MS_DEFAULT
_latest_fast = {}
_latest_slow = {}
_latest_errors = {}
_last_payload_ts = 0
_last_seq = 0
_worker_thread = None
_stop_requested = False
_poll_paused = False
_uart_lock = None
_COMMAND_MAP = {}

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


async def _send_json(uart, lock, payload, frame_type=None):
    if frame_type and "type" not in payload:
        payload["type"] = frame_type
    data = None
    try:
        data = json.dumps(payload) + "\n"
    except Exception as exc:
        print("[pr_offload] json encode error", exc)
        return False
    async with lock:
        try:
            uart.write(data)
            return True
        except Exception as exc:
            print("[pr_offload] uart write error", exc)
            return False


async def command_task(main_uart, uart_lock):
    buffer = b""
    try:
        while not _stop_requested:
            if main_uart.any():
                chunk = main_uart.read()
                if chunk:
                    buffer += chunk
                    while True:
                        newline = buffer.find(b"\n")
                        if newline == -1:
                            break
                        line = buffer[:newline].strip()
                        buffer = buffer[newline + 1 :]
                        if not line:
                            continue
                        resp, action = _handle_command_line(line)
                        if resp:
                            await _send_json(main_uart, uart_lock, resp, frame_type="resp")
                            if action == "reset":
                                await asyncio.sleep_ms(200)
                                machine.reset()
            await asyncio.sleep_ms(20)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print("[pr_offload] command task error", exc)


def _handle_command_line(line):
    if isinstance(line, bytes):
        try:
            line = line.decode()
        except Exception:
            line = line.decode("utf-8", "ignore")
    try:
        payload = json.loads(line)
    except Exception as exc:
        return ({"type": "resp", "ok": False, "error": "bad json", "detail": repr(exc)}, None)
    if not isinstance(payload, dict):
        return ({"type": "resp", "ok": False, "error": "command must be object"}, None)
    req_id = payload.get("req_id")
    cmd = payload.get("cmd")
    if not cmd:
        resp = {"type": "resp", "ok": False, "error": "missing cmd"}
        if req_id is not None:
            resp["req_id"] = req_id
        return (resp, None)
    cmd = cmd.lower()
    handler = _COMMAND_MAP.get(cmd)
    if not handler:
        resp = {"type": "resp", "ok": False, "cmd": cmd, "error": "unknown cmd"}
        if req_id is not None:
            resp["req_id"] = req_id
        return (resp, None)
    try:
        resp, action = handler(payload)
    except Exception as exc:
        resp = {"type": "resp", "ok": False, "cmd": cmd, "error": repr(exc)}
        if req_id is not None:
            resp["req_id"] = req_id
        return (resp, None)
    if resp is None:
        resp = {}
    resp.setdefault("cmd", cmd)
    resp.setdefault("ok", True)
    if req_id is not None:
        resp.setdefault("req_id", req_id)
    try:
        print("[offload cmd]", payload, "->", resp)
    except Exception:
        pass
    return (resp, action)


async def pr_poll_task(pr, main_uart, uart_lock):
    global _latest_fast, _latest_slow, _latest_errors, _last_payload_ts, _last_seq

    next_slow = time.ticks_add(time.ticks_ms(), _slow_interval_ms)
    cache = {}
    seq = 0
    slow_snapshot = {}
    slow_interval_last = _slow_interval_ms

    while not _stop_requested:
        if _poll_paused:
            await asyncio.sleep_ms(100)
            continue
        current_fast_ms = _fast_interval_ms
        current_slow_ms = _slow_interval_ms
        payload = {
            "type": "telemetry",
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

        await _send_json(main_uart, uart_lock, payload)

        _latest_fast = payload["fast"].copy()
        _latest_slow = payload["slow"].copy()
        _latest_errors = payload["errors"].copy()
        _last_payload_ts = payload["ts"]
        _last_seq = seq

        seq = (seq + 1) & 0xFFFF
        await asyncio.sleep_ms(current_fast_ms)

    print("[pr_offload] poll task exiting")


async def main():
    # HW constants are defined from the Phaserunner perspective (PR_UART_TX is the line driven by the PR).
    # From the ESP32 perspective we need to cross them: TX pin drives the PR's RX line, so use PR_UART_RX.
    pr_uart = machine.UART(
        PR_UART_ID,
        baudrate=PR_UART_BAUD,
        tx=machine.Pin(PR_UART_RX),
        rx=machine.Pin(PR_UART_TX),
        timeout=300,
    )
    main_uart = machine.UART(
        MAIN_UART_ID,
        baudrate=MAIN_UART_BAUD,
        tx=machine.Pin(MAIN_UART_TX),
        rx=machine.Pin(MAIN_UART_RX),
        timeout=20,
    )
    pr = Phaserunner(pr_uart)
    uart_lock = asyncio.Lock()
    poll_task = asyncio.create_task(pr_poll_task(pr, main_uart, uart_lock))
    cmd_task = asyncio.create_task(command_task(main_uart, uart_lock))
    try:
        await poll_task
    finally:
        cmd_task.cancel()
        try:
            await cmd_task
        except Exception:
            pass


def _thread_entry():
    global _worker_thread
    try:
        asyncio.run(main())
    except Exception as exc:
        print("PR-offload error:", exc)
    finally:
        _worker_thread = None


def start():
    """Start the PR-offload worker in a background thread if not already running."""
    global _worker_thread, _stop_requested
    if _worker_thread is not None:
        return False
    _stop_requested = False
    _worker_thread = _thread.start_new_thread(_thread_entry, ())
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


def _cmd_ping(_payload):
    return ({"ts": time.ticks_ms(), "seq": _last_seq}, None)


def _cmd_snapshot(_payload):
    return (get_snapshot(), None)


def _cmd_errors(_payload):
    return ({"errors": get_errors()}, None)


def _cmd_set_fast(payload):
    ms = payload.get("ms")
    if ms is None:
        raise ValueError("missing ms")
    return ({"fast_ms": set_fast_interval(ms)}, None)


def _cmd_set_slow(payload):
    ms = payload.get("ms")
    if ms is None:
        raise ValueError("missing ms")
    return ({"slow_ms": set_slow_interval(ms)}, None)


def _cmd_set_rate(payload):
    fast = payload.get("fast_ms")
    slow = payload.get("slow_ms")
    resp = {}
    if fast is not None:
        resp["fast_ms"] = set_fast_interval(fast)
    if slow is not None:
        resp["slow_ms"] = set_slow_interval(slow)
    if not resp:
        raise ValueError("no fast_ms/slow_ms provided")
    return (resp, None)


def _cmd_poll(payload):
    global _poll_paused
    action = payload.get("action", "").lower()
    if action in ("pause", "stop"):
        _poll_paused = True
    elif action in ("resume", "start"):
        _poll_paused = False
    else:
        raise ValueError("action must be pause/stop/start/resume")
    return ({"paused": _poll_paused}, None)


def _cmd_status(_payload):
    return (
        {
            "running": is_running(),
            "paused": _poll_paused,
            "fast_ms": _fast_interval_ms,
            "slow_ms": _slow_interval_ms,
            "seq": _last_seq,
            "ts": _last_payload_ts,
            "fw": FW_VERSION,
            "protocol": PROTOCOL_VERSION,
        },
        None,
    )


def _cmd_reboot(_payload):
    return ({"message": "resetting"}, "reset")


def _cmd_sleep(_payload):
    raise RuntimeError(
        "Deep sleep wake requires RTC-capable pin (0,2,4,12-15,25-27,32-39); GPIO18/19 cannot wake"
    )


def _cmd_version(_payload):
    return ({"fw": FW_VERSION, "protocol": PROTOCOL_VERSION}, None)


_COMMAND_MAP = {
    "ping": _cmd_ping,
    "snapshot": _cmd_snapshot,
    "errors": _cmd_errors,
    "set_fast": _cmd_set_fast,
    "set_slow": _cmd_set_slow,
    "set_rate": _cmd_set_rate,
    "poll": _cmd_poll,
    "status": _cmd_status,
    "reboot": _cmd_reboot,
    "sleep": _cmd_sleep,
    "version": _cmd_version,
}
