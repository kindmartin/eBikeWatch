"""Phaserunner offload firmware with binary bridge protocol."""

import time
import sys

import _thread
import machine
import uasyncio as asyncio

try:
    import esp32  # type: ignore
except ImportError:  # pragma: no cover
    esp32 = None  # type: ignore

try:
    import ustruct as struct  # type: ignore
except ImportError:  # pragma: no cover
    import struct  # type: ignore

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
try:
    from HW import WAKE_PINS as _HW_WAKE_PINS  # type: ignore
except ImportError:  # pragma: no cover - optional config
    _HW_WAKE_PINS = None
except Exception:  # pragma: no cover - optional config
    _HW_WAKE_PINS = None
from phaserunner import Phaserunner
from registers import PR_REGISTERS
import bridge_protocol as proto


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
_main_sessions = 0
_main_last_token = None
_debug_logging = False
_wake_pin_configured = False
_force_slow_once = False
_register_state = {}
_worker_thread = None
_SLEEP_DELAY_MS = 10_000
_sleep_task = None
_sleep_pending = False


def _resolve_wake_pins():
    raw = _HW_WAKE_PINS if _HW_WAKE_PINS is not None else (MAIN_UART_RX,)
    if not isinstance(raw, (list, tuple)):
        raw = (raw,)
    pins = []
    for candidate in raw:
        try:
            value = int(candidate)
        except Exception:
            continue
        if value < 0:
            continue
        if value not in pins:
            pins.append(value)
    if not pins:
        pins.append(int(MAIN_UART_TX))
    return tuple(pins)


_WAKE_PIN_LIST = _resolve_wake_pins()
_wake_pin_objects = []

MSP_FLAG_SLOW_INCLUDED = 0x01
_BOOT_SAMPLE_REGS = (
    "battery_voltage",
    "battery_current",
    "vehicle_speed",
    "controller_temp",
)
_boot_banner_printed = False


def _format_reg_details(name):
    meta = PR_REGISTERS.get(name) or {}
    addr = meta.get("addr")
    unit = meta.get("unit", "")
    scale = meta.get("scale")
    addr_txt = "0x{:04X}".format(addr) if isinstance(addr, int) else "??"
    scale_txt = "{:.3g}".format(scale) if isinstance(scale, (int, float)) else "?"
    unit_txt = unit or "-"
    return "{:<16} addr={} scale={} unit={}".format(name, addr_txt, scale_txt, unit_txt)


def _log_register_block(label, names):
    if not names:
        return
    _log("boot: {} regs ({}): {}".format(label, len(names), ", ".join(names)))
    for name in names:
        _log("boot:    {}".format(_format_reg_details(name)))


def _probe_phaserunner_once():
    try:
        uart = machine.UART(
            PR_UART_ID,
            baudrate=PR_UART_BAUD,
            tx=machine.Pin(PR_UART_RX),
            rx=machine.Pin(PR_UART_TX),
            timeout=200,
            timeout_char=2,
        )
    except Exception as exc:
        _log("boot: unable to open PR UART", exc)
        return
    try:
        pr = Phaserunner(uart)
        samples = []
        for name in _BOOT_SAMPLE_REGS:
            try:
                value = pr.read_value(name)
                meta = PR_REGISTERS.get(name) or {}
                unit = meta.get("unit", "")
                if isinstance(value, (int, float)):
                    value_txt = "{:.2f}".format(value)
                else:
                    value_txt = str(value)
                samples.append("{}={}{}".format(name, value_txt, unit))
            except Exception as exc:
                samples.append("{}=!{}".format(name, getattr(exc, "args", [exc])[0]))
        _log("boot: Phaserunner probe " + ", ".join(samples))
    except Exception as exc:
        _log("boot: Phaserunner probe failed", exc)
    finally:
        try:
            uart.deinit()
        except Exception:
            pass


def _log_boot_banner():
    global _boot_banner_printed
    if _boot_banner_printed:
        return
    _boot_banner_printed = True
    _log("boot: FW {} | MSP proto {} | fast {}ms | slow {}ms".format(
        FW_VERSION,
        PROTOCOL_VERSION,
        FAST_INTERVAL_MS_DEFAULT,
        SLOW_INTERVAL_MS_DEFAULT,
    ))
    _log("boot: MSP telemetry flag slow=0x{:02X}".format(MSP_FLAG_SLOW_INCLUDED))
    _log_register_block("FAST", FAST_REGS)
    _log_register_block("SLOW", SLOW_REGS)
    _probe_phaserunner_once()


def _log(*args):
    try:
        print("[pr_offload]", *args)
    except Exception:
        pass


async def _delayed_sleep_worker(delay_ms):
    global _sleep_task, _sleep_pending
    try:
        if delay_ms > 0:
            _log("sleepNow armed; sleeping in {} ms".format(delay_ms))
            await asyncio.sleep_ms(delay_ms)
        else:
            _log("sleepNow armed without delay")
        _configure_wake_pins()
        await asyncio.sleep_ms(200)
        _log("entering deep sleep")
        machine.deepsleep()
    except asyncio.CancelledError:
        _log("sleepNow request cancelled")
        raise
    finally:
        _sleep_pending = False
        _sleep_task = None


def _schedule_delayed_sleep(delay_ms=_SLEEP_DELAY_MS):
    global _sleep_task, _sleep_pending
    try:
        delay_ms = int(delay_ms)
    except Exception:
        delay_ms = _SLEEP_DELAY_MS
    if delay_ms < 0:
        delay_ms = 0
    _sleep_pending = True
    if _sleep_task is not None:
        try:
            _sleep_task.cancel()
        except Exception:
            pass
        _sleep_task = None
    create = getattr(asyncio, "create_task", None)
    if callable(create):
        _sleep_task = create(_delayed_sleep_worker(delay_ms))
    else:
        loop = asyncio.get_event_loop()
        _sleep_task = loop.create_task(_delayed_sleep_worker(delay_ms))


def _is_coroutine(obj):
    """Return True when the object behaves like a coroutine."""
    checker = getattr(asyncio, "iscoroutine", None)
    if callable(checker):
        try:
            return bool(checker(obj))
        except Exception:
            pass
    # MicroPython coroutine objects are generators with send/throw hooks.
    return hasattr(obj, "send") and hasattr(obj, "throw")


def _configure_wake_pins():
    """Configure all requested wake pins; success if any path works."""
    global _wake_pin_configured, _wake_pin_objects
    pins = _WAKE_PIN_LIST or (MAIN_UART_RX,)
    wake_high = getattr(machine.Pin, "WAKE_HIGH", 1)
    pull_down = getattr(machine.Pin, "PULL_DOWN", None)
    _wake_pin_objects = []
    errors = []
    successes = []

    for idx, pin_id in enumerate(pins):
        try:
            if pull_down is None:
                pin = machine.Pin(pin_id, machine.Pin.IN)
            else:
                pin = machine.Pin(pin_id, machine.Pin.IN, pull_down)
        except Exception as exc:  # pragma: no cover - hardware dependent
            errors.append(("Pin GPIO{}".format(pin_id), exc))
            continue

        _wake_pin_objects.append(pin)
        methods = []

        # Prefer RTC/esp32 helpers for the first pin (only one ext0 source allowed).
        if idx == 0:
            try:
                rtc = machine.RTC()
                wake_fn = getattr(rtc, "wake_on_ext0", None)
                if callable(wake_fn):
                    wake_fn(pin=pin, level=wake_high)
                    methods.append("RTC")
            except Exception as exc:  # pragma: no cover - hardware dependent
                errors.append(("RTC GPIO{}".format(pin_id), exc))

            if esp32 is not None:
                try:
                    wake_level = getattr(esp32, "WAKEUP_EXT0_HIGH", wake_high)
                    wake_fn = getattr(esp32, "wake_on_ext0", None)
                    if callable(wake_fn):
                        wake_fn(pin=pin, level=wake_level)
                        methods.append("esp32")
                    else:
                        errors.append(("esp32 GPIO{}".format(pin_id), "wake_on_ext0 missing"))
                except Exception as exc:  # pragma: no cover - hardware dependent
                    errors.append(("esp32 GPIO{}".format(pin_id), exc))
            else:
                errors.append(("esp32", "module unavailable"))

        if methods:
            successes.append((pin_id, methods))

    _wake_pin_configured = bool(successes)
    if successes:
        for pin_id, methods in successes:
            _log(
                "wake pin configured on GPIO{} via {}".format(
                    pin_id, "/".join(methods)
                )
            )
        first_pin = successes[0][0]
        _log(
            "wake requires GPIO{} held HIGH during deep sleep".format(
                first_pin
            )
        )
        return True

    for source, exc in errors:
        _log("wake pin setup failed using {}".format(source), exc)
    if not errors:
        _log("wake pin setup failed", "wake helpers unavailable")
    return False

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

_latest_fast = {name: None for name in FAST_REGS}
_latest_slow = {name: None for name in SLOW_REGS}


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


def _read_register_block(pr, names, state=None):
    if state is None:
        state = _register_state
    values = {}
    errors = {}
    for name in names:
        value = _safe_read(pr, name, state)
        values[name] = value
        entry = state.get(name) or {}
        last_error = entry.get("last_error")
        if last_error:
            errors[name] = last_error
    return values, errors


def _pack_float(value):
    if value is None:
        value = float("nan")
    try:
        value = float(value)
    except Exception:
        value = float("nan")
    return struct.pack("<f", value)


def _build_response_payload(req_id, status=proto.RESP_OK, extra=b""):
    if not isinstance(extra, (bytes, bytearray)):
        extra = bytes(extra)
    buf = bytearray(struct.pack("<HB", req_id & 0xFFFF, status & 0xFF))
    if extra:
        buf.extend(extra)
    return bytes(buf)


def _build_telemetry_payload(flags, seq, timestamp, fast_values, slow_values=None):
    payload = bytearray()
    payload.append(flags & 0xFF)
    payload.extend(struct.pack("<H", seq & 0xFFFF))
    payload.extend(struct.pack("<I", timestamp & 0xFFFFFFFF))
    for name in FAST_REGS:
        payload.extend(_pack_float(fast_values.get(name)))
    if flags & MSP_FLAG_SLOW_INCLUDED:
        slow_block = slow_values or {}
        for name in SLOW_REGS:
            payload.extend(_pack_float(slow_block.get(name)))
    return bytes(payload)


def _encode_string(value, max_len=48):
    try:
        data = str(value or "").encode("utf-8")
    except Exception:
        data = b""
    if len(data) > max_len:
        data = data[:max_len]
    return bytes([len(data)]) + data


async def _send_msp(main_uart, uart_lock, cmd, payload=b""):
    frame = proto.build_frame(proto.DIR_FROM_DEVICE, cmd, payload)
    async with uart_lock:
        try:
            main_uart.write(frame)
        except Exception as exc:
            _log("uart write error", exc)


async def _send_boot_version(main_uart, uart_lock):
    _log("announcing boot version", FW_VERSION)
    extra = struct.pack("<B", PROTOCOL_VERSION)
    fw_bytes = FW_VERSION.encode("utf-8")[:60]
    extra += bytes([len(fw_bytes)]) + fw_bytes
    payload = _build_response_payload(0, proto.RESP_OK, extra)
    await _send_msp(main_uart, uart_lock, proto.CMD_VERSION, payload)


def _ensure_command_handlers():
    global _COMMAND_MAP, _force_slow_once, _poll_paused, _main_sessions, _main_last_token
    if _COMMAND_MAP:
        return

    def _cmd_ping(_req_id, _body):
        extra = struct.pack("<IH", time.ticks_ms() & 0xFFFFFFFF, _last_seq & 0xFFFF)
        return (proto.RESP_OK, extra, None)

    def _cmd_snapshot(_req_id, _body):
        global _force_slow_once
        _force_slow_once = True
        return (proto.RESP_OK, b"", None)

    def _cmd_set_rate(_req_id, body):
        fast = slow = 0
        if len(body) >= 2:
            fast = struct.unpack_from("<H", body, 0)[0]
        if len(body) >= 4:
            slow = struct.unpack_from("<H", body, 2)[0]
        if fast:
            set_fast_interval(fast)
        if slow:
            set_slow_interval(slow)
        extra = struct.pack("<HH", _fast_interval_ms, _slow_interval_ms)
        return (proto.RESP_OK, extra, None)

    def _cmd_poll(_req_id, body):
        global _poll_paused
        action = body[0] if body else 0
        if action == 0:
            _poll_paused = True
        elif action == 1:
            _poll_paused = False
        else:
            return (proto.RESP_UNSUPPORTED, b"", None)
        extra = struct.pack("<B", int(_poll_paused))
        return (proto.RESP_OK, extra, None)

    def _cmd_status(_req_id, _body):
        extra = struct.pack(
            "<BBHHHI",
            int(is_running()),
            int(_poll_paused),
            _fast_interval_ms & 0xFFFF,
            _slow_interval_ms & 0xFFFF,
            _last_seq & 0xFFFF,
            _last_payload_ts & 0xFFFFFFFF,
        )
        extra += struct.pack("<B", PROTOCOL_VERSION)
        return (proto.RESP_OK, extra, None)

    def _cmd_reboot(_req_id, _body):
        _log("reboot requested")
        return (proto.RESP_OK, b"", "reset")

    def _cmd_sleep_now(_req_id, body):
        delay_ms = _SLEEP_DELAY_MS
        delay_s = None
        if body and len(body) >= 2:
            try:
                delay_s = int(struct.unpack_from("<H", body, 0)[0]) & 0xFFFF
            except Exception:
                delay_s = None
        if delay_s is not None:
            delay_ms = delay_s * 1000
        _schedule_delayed_sleep(delay_ms)
        _log("sleepNow requested; offload will sleep in {} ms".format(delay_ms))
        extra = struct.pack("<I", delay_ms & 0xFFFFFFFF)
        return (proto.RESP_OK, extra, None)

    def _cmd_wifi_connect(_req_id, _body):
        _log("wifiConnect requested")
        try:
            import wifiConnect  # type: ignore  # noqa: F401
        except Exception as exc:
            _log("wifiConnect failed", exc)
            return (proto.RESP_ERROR, _encode_string(exc), None)
        return (proto.RESP_OK, b"", None)

    def _cmd_main_online(_req_id, body):
        global _main_sessions, _main_last_token
        host_ts = 0
        if len(body) >= 4:
            host_ts = struct.unpack_from("<I", body, 0)[0]
        if host_ts != _main_last_token:
            _main_sessions += 1
            _main_last_token = host_ts
            _log("main ESP connected", "session=", _main_sessions)
        session_bytes = struct.pack("<H", _main_sessions & 0xFFFF)
        return (proto.RESP_OK, session_bytes, None)

    def _cmd_version(_req_id, _body):
        fw_bytes = FW_VERSION.encode("utf-8")[:60]
        extra = struct.pack("<B", PROTOCOL_VERSION) + bytes([len(fw_bytes)]) + fw_bytes
        return (proto.RESP_OK, extra, None)

    def _cmd_debug(_req_id, body):
        enabled = bool(body[0]) if body else False
        set_debug_logging(enabled)
        return (proto.RESP_OK, struct.pack("<B", int(enabled)), None)

    _COMMAND_MAP = {
        proto.CMD_PING: _cmd_ping,
        proto.CMD_SNAPSHOT: _cmd_snapshot,
        proto.CMD_SET_RATE: _cmd_set_rate,
        proto.CMD_POLL_CTRL: _cmd_poll,
        proto.CMD_STATUS: _cmd_status,
        proto.CMD_REBOOT: _cmd_reboot,
        proto.CMD_SLEEP_NOW: _cmd_sleep_now,
        proto.CMD_WIFI_CONNECT: _cmd_wifi_connect,
        proto.CMD_MAIN_ONLINE: _cmd_main_online,
        proto.CMD_VERSION: _cmd_version,
        proto.CMD_DEBUG: _cmd_debug,
    }


async def _process_command_frame(main_uart, uart_lock, frame):
    cmd = frame.get("cmd")
    payload = frame.get("payload") or b""
    if len(payload) >= 2:
        req_id = struct.unpack_from("<H", payload, 0)[0]
        body = payload[2:]
    else:
        req_id = 0
        body = b""
    handler = _COMMAND_MAP.get(cmd)
    if not handler:
        resp = _build_response_payload(req_id, proto.RESP_UNSUPPORTED)
        await _send_msp(main_uart, uart_lock, cmd, resp)
        return
    try:
        result = handler(req_id, body)
        if _is_coroutine(result):
            status, extra, action = await result
        else:
            status, extra, action = result
    except Exception as exc:
        status = proto.RESP_ERROR
        extra = _encode_string(exc)
        action = None
    resp_payload = _build_response_payload(req_id, status, extra)
    await _send_msp(main_uart, uart_lock, cmd, resp_payload)
    if action == "reset":
        await asyncio.sleep_ms(200)
        machine.reset()
    elif action == "sleep_now":
        _configure_wake_pins()
        await asyncio.sleep_ms(200)
        _log("entering deep sleep")
        machine.deepsleep()


async def command_task(main_uart, uart_lock):
    parser = proto.MSPParser()
    while not _stop_requested:
        try:
            data = main_uart.read()
            if data:
                frames = parser.feed(data)
                for frame in frames:
                    if frame.get("direction") != proto.DIR_TO_DEVICE:
                        continue
                    await _process_command_frame(main_uart, uart_lock, frame)
            else:
                await asyncio.sleep_ms(10)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log("command task error", exc)
            sys.print_exception(exc)
            await asyncio.sleep_ms(50)


async def pr_poll_task(pr, main_uart, uart_lock):
    global _latest_fast, _latest_slow, _latest_errors, _last_payload_ts, _last_seq, _force_slow_once
    _ensure_command_handlers()
    next_slow_due = time.ticks_ms()
    while not _stop_requested:
        try:
            if _sleep_pending:
                await asyncio.sleep_ms(50)
                continue
            if _poll_paused:
                await asyncio.sleep_ms(50)
                continue
            loop_start = time.ticks_ms()
            fast_values, fast_errors = _read_register_block(pr, FAST_REGS)
            include_slow = _force_slow_once or time.ticks_diff(loop_start, next_slow_due) >= 0
            slow_values = _latest_slow
            slow_errors = {}
            if include_slow:
                slow_values, slow_errors = _read_register_block(pr, SLOW_REGS)
                next_slow_due = time.ticks_add(loop_start, _slow_interval_ms)
                _force_slow_once = False
            errors = dict(fast_errors)
            errors.update(slow_errors)
            _latest_fast = fast_values
            if include_slow:
                _latest_slow = slow_values
            _latest_errors = errors
            _last_seq = (_last_seq + 1) & 0xFFFF
            _last_payload_ts = loop_start & 0xFFFFFFFF
            flags = MSP_FLAG_SLOW_INCLUDED if include_slow else 0
            slow_payload = _latest_slow if include_slow else None
            payload = _build_telemetry_payload(
                flags,
                _last_seq,
                _last_payload_ts,
                _latest_fast,
                slow_payload,
            )
            await _send_msp(main_uart, uart_lock, proto.CMD_TELEMETRY, payload)
            next_fast = time.ticks_add(loop_start, _fast_interval_ms)
            remaining = time.ticks_diff(next_fast, time.ticks_ms())
            if remaining > 0:
                await asyncio.sleep_ms(remaining)
            else:
                await asyncio.sleep_ms(5)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log("poll loop error", exc)
            sys.print_exception(exc)
            await asyncio.sleep_ms(50)


def get_slow_interval():
    """Return the current slow-loop interval in ms."""
    return _slow_interval_ms


def get_fast_interval():
    """Return the current fast-loop interval in ms."""
    return _fast_interval_ms


def set_fast_interval(ms):
    """Update the fast-loop interval in ms and clamp slow-loop accordingly."""
    global _fast_interval_ms, _slow_interval_ms
    ms = max(10, int(ms))
    _fast_interval_ms = ms
    if _slow_interval_ms < _fast_interval_ms:
        _slow_interval_ms = _fast_interval_ms
    return _fast_interval_ms


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


def is_running():
    """Return True while the polling loop is expected to run."""
    return not _stop_requested




def set_debug_logging(enabled: bool):
    """Enable or disable noisy command logging."""
    global _debug_logging
    _debug_logging = bool(enabled)
    return _debug_logging


# Emit a concise boot summary as soon as the module is imported on the offload ESP32.
try:  # pragma: no cover - cosmetic boot logging
    _log_boot_banner()
except Exception as exc:
    _log("boot: summary failed", exc)


async def _offload_main():
    global _stop_requested, _uart_lock
    _ensure_command_handlers()
    _stop_requested = False
    _uart_lock = asyncio.Lock()
    pr_uart = None
    main_uart = None
    try:
        main_uart = machine.UART(
            MAIN_UART_ID,
            baudrate=MAIN_UART_BAUD,
            tx=MAIN_UART_TX,
            rx=MAIN_UART_RX,
            timeout=40,
            timeout_char=8,
        )
        pr_uart = machine.UART(
            PR_UART_ID,
            baudrate=PR_UART_BAUD,
            tx=machine.Pin(PR_UART_RX),
            rx=machine.Pin(PR_UART_TX),
            timeout=200,
            timeout_char=2,
        )
        pr = Phaserunner(pr_uart)
    except Exception as exc:
        _log("uart init failed", exc)
        sys.print_exception(exc)
        raise

    await _send_boot_version(main_uart, _uart_lock)

    poll_task = asyncio.create_task(pr_poll_task(pr, main_uart, _uart_lock))
    cmd_task = asyncio.create_task(command_task(main_uart, _uart_lock))

    try:
        while not _stop_requested:
            await asyncio.sleep_ms(500)
    except asyncio.CancelledError:
        pass
    finally:
        _stop_requested = True
        for task in (poll_task, cmd_task):
            task.cancel()
        for task in (poll_task, cmd_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _log("task shutdown error", exc)
        await asyncio.sleep_ms(10)
        if pr_uart is not None:
            try:
                pr_uart.deinit()
            except Exception:
                pass
        if main_uart is not None:
            try:
                main_uart.deinit()
            except Exception:
                pass


def _asyncio_thread_runner():
    global _worker_thread
    try:
        asyncio.run(_offload_main())
    except Exception as exc:
        _log("async runner error", exc)
        sys.print_exception(exc)
    finally:
        _worker_thread = None


def start():
    global _worker_thread, _stop_requested
    if _worker_thread is not None:
        _log("worker already running (thread {})".format(_worker_thread))
        return False
    _stop_requested = False
    try:
        _worker_thread = _thread.start_new_thread(_asyncio_thread_runner, ())
        _log("async worker started on thread {}".format(_worker_thread))
    except Exception as exc:
        _worker_thread = None
        _log("unable to start worker", exc)
        sys.print_exception(exc)
        raise
    return True


def stop():
    global _stop_requested
    if not _stop_requested:
        _log("stop requested")
        _stop_requested = True
    return True


def main():
    started = start()
    if not started:
        _log("worker already running; no-op")
    return started


if __name__ == "__main__":  # pragma: no cover
    main()
