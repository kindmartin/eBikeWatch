"""Serial bridge reader that ingests PR-offload telemetry."""

try:
    import ujson as json  # type: ignore
except Exception:  # pragma: no cover - fallback for CPython tools
    import json

import _thread
from machine import UART
from time import sleep_ms, ticks_add, ticks_diff, ticks_ms

from HW import PR_UART_ID, PR_UART_TX, PR_UART_RX, PR_UART_BAUD


_REGISTER_UNITS = {
    "battery_current": "A",
    "vehicle_speed": "km/h",
    "motor_input_power": "W",
    "controller_temp": "C",
    "motor_temp": "C",
    "motor_rpm": "rpm",
    "battery_voltage": "V",
    "throttle_voltage": "V",
    "brake_voltage_1": "V",
    "digital_inputs": "",
    "warnings": "",
}


_STATE_ALIAS = {"vehicle_speed": "vehicle_speed_PR"}

_CMD_QUEUE = []
_CMD_LOCK = _thread.allocate_lock()
_PENDING_RESPONSES = {}
_PENDING_LOCK = _thread.allocate_lock()
_PAYLOAD_LOCK = _thread.allocate_lock()
_STATUS_LOCK = _thread.allocate_lock()

_NEXT_REQ_ID = 1
_LAST_PAYLOAD = None
_LAST_ERRORS = {}
_BRIDGE_STATUS = {
    "rx_frames": 0,
    "rx_errors": 0,
    "last_seq": 0,
    "last_ts": 0,
    "last_rx_ms": 0,
    "last_error": "",
}


def _with_lock(lock, fn):
    lock.acquire()
    try:
        return fn()
    finally:
        lock.release()


def _queue_command(payload):
    def _append():
        _CMD_QUEUE.append(payload)

    _with_lock(_CMD_LOCK, _append)


def _pop_command():
    def _pop():
        if _CMD_QUEUE:
            return _CMD_QUEUE.pop(0)
        return None

    return _with_lock(_CMD_LOCK, _pop)


def _store_response(payload):
    req_id = payload.get("req_id")
    if req_id is None:
        return

    def _store():
        _PENDING_RESPONSES[req_id] = payload

    _with_lock(_PENDING_LOCK, _store)


def _record_error(message):
    def _update():
        _BRIDGE_STATUS["last_error"] = str(message)
        _BRIDGE_STATUS["rx_errors"] += 1

    _with_lock(_STATUS_LOCK, _update)


def _set_last_payload(payload):
    def _update():
        global _LAST_PAYLOAD, _LAST_ERRORS
        _LAST_PAYLOAD = payload
        _LAST_ERRORS = payload.get("errors", {}).copy()

    _with_lock(_PAYLOAD_LOCK, _update)


def _update_status(seq, ts):
    now_ms = ticks_ms()

    def _apply():
        _BRIDGE_STATUS["rx_frames"] += 1
        _BRIDGE_STATUS["last_seq"] = seq
        _BRIDGE_STATUS["last_ts"] = ts
        _BRIDGE_STATUS["last_rx_ms"] = now_ms
        _BRIDGE_STATUS["last_error"] = ""

    _with_lock(_STATUS_LOCK, _apply)


def _publish_value(state, name, value):
    target = _STATE_ALIAS.get(name, name)
    unit = _REGISTER_UNITS.get(name, "")
    state.set_pr(target, value, unit)


def _update_calc_voltage(state, fast_block):
    current_val = fast_block.get("battery_current")
    power_val = fast_block.get("motor_input_power")
    calc_v = None
    try:
        if current_val not in (None, 0):
            current_f = float(current_val)
            if abs(current_f) > 1e-3 and power_val is not None:
                calc_v = float(power_val) / current_f
    except Exception:
        calc_v = None
    if calc_v is not None and calc_v == calc_v:
        state.set_pr("batt_voltage_calc", calc_v, "V")
    else:
        state.set_pr("batt_voltage_calc", None, "V")


def _handle_telemetry(state, payload):
    fast = payload.get("fast") or {}
    slow = payload.get("slow") or {}
    errors = payload.get("errors") or {}
    for name, value in fast.items():
        _publish_value(state, name, value)
    for name, value in slow.items():
        _publish_value(state, name, value)
    _update_calc_voltage(state, fast)
    seq = payload.get("seq", 0)
    ts = payload.get("ts", 0)
    payload_copy = {
        "type": "telemetry",
        "seq": seq,
        "ts": ts,
        "fast": dict(fast),
        "slow": dict(slow),
        "errors": dict(errors),
    }
    _set_last_payload(payload_copy)
    _update_status(seq, ts)


def _handle_line(state, line):
    if isinstance(line, bytes):
        try:
            line = line.decode()
        except Exception:
            line = line.decode("utf-8", "ignore")
    try:
        payload = json.loads(line)
    except Exception as exc:
        _record_error("json {}".format(exc))
        return
    frame_type = payload.get("type") or "telemetry"
    if frame_type == "resp":
        _store_response(payload)
        try:
            print("[bridge] RESP", payload)
        except Exception:
            pass
        return
    if frame_type != "telemetry":
        return
    _handle_telemetry(state, payload)


def _write_command(uart, payload):
    try:
        uart.write(json.dumps(payload) + "\n")
    except Exception as exc:
        _record_error("uart write {}".format(exc))


def phaserunner_worker(
    state,
    *,
    stop_predicate,
    fast_interval_source,
    slow_interval_source,
):
    # Keep the bridge UART responsive enough for command traffic while still
    # allowing full telemetry lines to stream in from the offload MCU.
    uart = UART(
        PR_UART_ID,
        baudrate=PR_UART_BAUD,
        tx=PR_UART_TX,
        rx=PR_UART_RX,
        timeout=40,
        timeout_char=8,
    )
    try:
        try:
            fast_ms = int(fast_interval_source())
        except Exception:
            fast_ms = 50
        try:
            slow_ms = int(slow_interval_source())
        except Exception:
            slow_ms = 1000
        send_command({"cmd": "set_rate", "fast_ms": fast_ms, "slow_ms": slow_ms}, wait_ms=0)
        send_command({"cmd": "poll", "action": "start"}, wait_ms=0)
    except Exception:
        pass
    while not stop_predicate():
        cmd = _pop_command()
        if cmd is not None:
            _write_command(uart, cmd)
        line = uart.readline()
        if line:
            line = line.strip()
            if line:
                _handle_line(state, line)
        else:
            sleep_ms(10)
    uart.deinit()


def send_command(cmd, *, wait_ms=0):
    """Queue a command for the PR-offload MCU; optionally wait for the reply."""
    global _NEXT_REQ_ID
    if not isinstance(cmd, dict):
        raise ValueError("command must be dict")
    payload = dict(cmd)

    def _enqueue():
        global _NEXT_REQ_ID
        req_id = _NEXT_REQ_ID
        _NEXT_REQ_ID = 1 if _NEXT_REQ_ID >= 0x7FFFFFFF else _NEXT_REQ_ID + 1
        payload["req_id"] = req_id
        _CMD_QUEUE.append(payload)
        return req_id

    req_id = _with_lock(_CMD_LOCK, _enqueue)
    if wait_ms and wait_ms > 0:
        deadline = ticks_add(ticks_ms(), int(wait_ms))
        while ticks_diff(deadline, ticks_ms()) > 0:
            def _take():
                return _PENDING_RESPONSES.pop(req_id, None)

            resp = _with_lock(_PENDING_LOCK, _take)
            if resp is not None:
                return resp
            sleep_ms(20)
        raise RuntimeError("command timeout")
    return {"req_id": req_id}


def get_bridge_status():
    def _copy():
        return dict(_BRIDGE_STATUS)

    return _with_lock(_STATUS_LOCK, _copy)


def get_latest_payload():
    def _copy():
        if _LAST_PAYLOAD is None:
            return None
        result = dict(_LAST_PAYLOAD)
        result["fast"] = dict(_LAST_PAYLOAD.get("fast", {}))
        result["slow"] = dict(_LAST_PAYLOAD.get("slow", {}))
        result["errors"] = dict(_LAST_PAYLOAD.get("errors", {}))
        return result

    return _with_lock(_PAYLOAD_LOCK, _copy)


def get_last_errors():
    def _copy():
        return dict(_LAST_ERRORS)

    return _with_lock(_PAYLOAD_LOCK, _copy)


__all__ = [
    "phaserunner_worker",
    "send_command",
    "get_bridge_status",
    "get_latest_payload",
    "get_last_errors",
]
