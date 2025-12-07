"""Serial bridge reader that ingests PR-offload telemetry over MSP."""

import _thread
from machine import UART  # type: ignore
from time import sleep_ms, ticks_add, ticks_diff, ticks_ms

try:
    import ustruct as struct  # type: ignore
except Exception:  # pragma: no cover
    import struct  # type: ignore

from HW import PR_UART_ID, PR_UART_TX, PR_UART_RX, PR_UART_BAUD
from runtime import bridge_protocol as proto


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
    "last_event": None,
}

MSP_FLAG_SLOW_INCLUDED = 0x01

FAST_REGS = (
    "battery_current",
    "vehicle_speed",
    "motor_input_power",
)

SLOW_REGS = (
    "controller_temp",
    "motor_temp",
    "motor_rpm",
    "battery_voltage",
    "throttle_voltage",
    "brake_voltage_1",
    "digital_inputs",
    "warnings",
)

_LAST_SLOW_VALUES = {name: None for name in SLOW_REGS}

_COMMAND_NAME_TO_ID = {
    "ping": proto.CMD_PING,
    "snapshot": proto.CMD_SNAPSHOT,
    "set_rate": proto.CMD_SET_RATE,
    "set_fast": proto.CMD_SET_RATE,
    "set_slow": proto.CMD_SET_RATE,
    "poll": proto.CMD_POLL_CTRL,
    "status": proto.CMD_STATUS,
    "reboot": proto.CMD_REBOOT,
    "sleep": proto.CMD_SLEEP_NOW,
    "sleep_now": proto.CMD_SLEEP_NOW,
    "sleepnow": proto.CMD_SLEEP_NOW,
    "wifi_connect": proto.CMD_WIFI_CONNECT,
    "main_online": proto.CMD_MAIN_ONLINE,
    "version": proto.CMD_VERSION,
    "debug": proto.CMD_DEBUG,
}

_POLL_ACTION_TO_BYTE = {
    "stop": 0,
    "pause": 0,
    "0": 0,
    0: 0,
    False: 0,
    "start": 1,
    "resume": 1,
    "run": 1,
    "1": 1,
    1: 1,
    True: 1,
}


def _with_lock(lock, fn):
    lock.acquire()
    try:
        return fn()
    finally:
        lock.release()

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


def _read_float(data, offset):
    value = struct.unpack_from("<f", data, offset)[0]
    if value != value:  # NaN check
        return None
    return value


def _decode_telemetry_payload(payload):
    min_len = 1 + 2 + 4 + len(FAST_REGS) * 4
    if len(payload) < min_len:
        _record_error("telemetry short {}".format(len(payload)))
        return None
    flags = payload[0]
    seq = struct.unpack_from("<H", payload, 1)[0]
    ts = struct.unpack_from("<I", payload, 3)[0]
    offset = 7
    fast = {}
    for name in FAST_REGS:
        fast[name] = _read_float(payload, offset)
        offset += 4
    if flags & MSP_FLAG_SLOW_INCLUDED:
        needed = len(SLOW_REGS) * 4
        if len(payload) < offset + needed:
            _record_error("telemetry slow short {}".format(len(payload)))
            return None
        slow = {}
        for name in SLOW_REGS:
            slow[name] = _read_float(payload, offset)
            offset += 4
        _LAST_SLOW_VALUES.update(slow)
    else:
        slow = dict(_LAST_SLOW_VALUES)
    errors = {}
    return {
        "seq": seq,
        "ts": ts,
        "fast": fast,
        "slow": slow,
        "errors": errors,
        "flags": flags,
    }


def _decode_response_payload(cmd, payload):
    if len(payload) < 3:
        _record_error("resp short {}".format(len(payload)))
        return None
    req_id, status = struct.unpack_from("<HB", payload, 0)
    extra = payload[3:]
    return {
        "req_id": req_id,
        "status": status,
        "cmd": cmd,
        "extra": extra,
    }


def _remember_event(event):
    def _store():
        _BRIDGE_STATUS["last_event"] = event

    _with_lock(_STATUS_LOCK, _store)


def _handle_frame(state, frame):
    if frame.get("direction") != proto.DIR_FROM_DEVICE:
        return
    cmd = frame.get("cmd")
    payload = frame.get("payload") or b""
    if cmd == proto.CMD_TELEMETRY:
        decoded = _decode_telemetry_payload(payload)
        if decoded:
            _handle_telemetry(state, decoded)
        return
    resp = _decode_response_payload(cmd, payload)
    if resp:
        _store_response(resp)
        _remember_event({"cmd": cmd, "status": resp["status"], "ts": ticks_ms()})


def _encode_command_body(name, payload):
    if name in ("set_rate", "set_fast", "set_slow"):
        fast = payload.get("fast_ms", payload.get("fast"))
        slow = payload.get("slow_ms", payload.get("slow"))
        if name == "set_fast":
            fast = payload.get("ms", payload.get("value", fast))
            slow = 0
        elif name == "set_slow":
            slow = payload.get("ms", payload.get("value", slow))
            fast = 0
        fast = int(fast or 0) & 0xFFFF
        slow = int(slow or 0) & 0xFFFF
        return struct.pack("<HH", fast, slow)
    if name == "poll":
        action = payload.get("action")
        if isinstance(action, str):
            key = action.strip().lower()
        else:
            key = action
        byte = _POLL_ACTION_TO_BYTE.get(key, 1)
        return bytes([byte & 0xFF])
    if name == "main_online":
        token = payload.get("host_ts")
        if token is None:
            token = ticks_ms()
        return struct.pack("<I", int(token) & 0xFFFFFFFF)
    if name == "debug":
        enabled = payload.get("enabled", payload.get("value", False))
        return struct.pack("<B", int(bool(enabled)))
    if name in ("sleep", "sleep_now", "sleepnow"):
        delay_s = payload.get("delay_s")
        if delay_s is None:
            return b""
        try:
            delay_val = max(0, int(delay_s))
        except Exception:
            delay_val = 0
        if delay_val > 0xFFFF:
            delay_val = 0xFFFF
        return struct.pack("<H", delay_val)
    return b""


def _build_command_frame(payload):
    cmd_name = str(payload.get("cmd") or "").lower()
    if not cmd_name:
        raise ValueError("command missing 'cmd'")
    cmd_id = _COMMAND_NAME_TO_ID.get(cmd_name)
    if cmd_id is None:
        raise ValueError("unsupported command: {}".format(cmd_name))
    body = _encode_command_body(cmd_name, payload)
    req_id = payload.get("req_id", 0)
    frame_payload = struct.pack("<H", req_id & 0xFFFF) + body
    return proto.build_frame(proto.DIR_TO_DEVICE, cmd_id, frame_payload)


def _write_command(uart, frame_bytes):
    try:
        uart.write(frame_bytes)
    except Exception as exc:
        _record_error("uart write {}".format(exc))


def phaserunner_worker(
    state,
    *,
    stop_predicate,
    fast_interval_source,
    slow_interval_source,
):
    uart = UART(
        PR_UART_ID,
        baudrate=PR_UART_BAUD,
        tx=PR_UART_TX,
        rx=PR_UART_RX,
        timeout=40,
        timeout_char=8,
    )
    parser = proto.MSPParser()
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
    try:
        while not stop_predicate():
            frame = _pop_command()
            if frame is not None:
                _write_command(uart, frame)
            chunk = uart.read()
            if chunk:
                frames = parser.feed(chunk)
                for parsed in frames:
                    _handle_frame(state, parsed)
            else:
                sleep_ms(10)
    finally:
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
        frame = _build_command_frame(payload)
        _CMD_QUEUE.append(frame)
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
