"""Helpers to persist trip counters across deep-sleep cycles using RTC memory."""

try:
    import ujson as json  # type: ignore
except ImportError:  # pragma: no cover - fallback for tooling
    import json  # type: ignore

try:  # pragma: no cover - MicroPython hardware API
    import machine  # type: ignore
except ImportError:  # pragma: no cover - host tooling
    machine = None  # type: ignore

try:
    from time import ticks_ms
except ImportError:  # pragma: no cover - host tooling
    import time

    def ticks_ms():
        return int(time.time() * 1000)


_RTC_MAGIC = "EBWRTC1|"
_MAX_BYTES = 480  # RTC memory limit is ~512 bytes; keep some margin
_SNAPSHOT_VERSION = 1


def _get_rtc():
    if machine is None:
        return None
    try:
        return machine.RTC()
    except Exception:
        return None


def _encode_snapshot(data):
    try:
        body = json.dumps(data, separators=(",", ":"))
    except Exception:
        return None
    payload = (_RTC_MAGIC + body).encode("utf-8")
    if len(payload) > _MAX_BYTES:
        return None
    return payload


def _decode_snapshot(blob):
    if not blob or not isinstance(blob, (bytes, bytearray)):
        return None
    try:
        text = blob.decode("utf-8")
    except Exception:
        return None
    if not text.startswith(_RTC_MAGIC):
        return None
    body = text[len(_RTC_MAGIC) :]
    try:
        data = json.loads(body)
    except Exception:
        return None
    if data.get("rev") != _SNAPSHOT_VERSION:
        return None
    return data


def clear_snapshot():
    rtc = _get_rtc()
    if rtc is None:
        return False
    try:
        rtc.memory(b"")
        return True
    except Exception:
        return False


def save_trip_snapshot(state):
    """Serialize key trip/energy counters into RTC memory."""

    rtc = _get_rtc()
    if rtc is None:
        return False

    def _float(attr):
        try:
            return float(getattr(state, attr, 0.0) or 0.0)
        except Exception:
            return 0.0

    def _int(attr):
        try:
            return int(getattr(state, attr, 0) or 0)
        except Exception:
            return 0

    snapshot = {
        "rev": _SNAPSHOT_VERSION,
        "stamp": int(ticks_ms() & 0xFFFFFFFF),
        "trip_pulses": _int("trip_pulses"),
        "trip_distance_m": _float("trip_distance_m"),
        "trip_distance_km": _float("trip_distance_km"),
        "km_total": _float("km_total"),
        "wh_total": _float("wh_total"),
    }

    payload = _encode_snapshot(snapshot)
    if payload is None:
        return False

    try:
        rtc.memory(payload)
        return True
    except Exception:
        return False


def restore_trip_snapshot(state, *, clear_on_success=True):
    """Restore counters from RTC memory into the provided AppState."""

    rtc = _get_rtc()
    if rtc is None:
        return None
    try:
        blob = rtc.memory()
    except Exception:
        return None
    data = _decode_snapshot(blob)
    if not data:
        return None

    def _apply_float(attr, key):
        value = data.get(key)
        if value is None:
            return
        try:
            setattr(state, attr, float(value))
        except Exception:
            pass

    def _apply_int(attr, key):
        value = data.get(key)
        if value is None:
            return
        try:
            setattr(state, attr, int(value))
        except Exception:
            pass

    _apply_int("trip_pulses", "trip_pulses")
    _apply_float("trip_distance_m", "trip_distance_m")
    _apply_float("trip_distance_km", "trip_distance_km")
    _apply_float("km_total", "km_total")
    _apply_float("wh_total", "wh_total")

    pulses = data.get("trip_pulses")
    if isinstance(pulses, (int, float)):
        try:
            state.trip_pulse_offset = int(pulses)
            state.trip_resume_pending = True
        except Exception:
            pass

    if clear_on_success:
        clear_snapshot()
    return data


__all__ = [
    "save_trip_snapshot",
    "restore_trip_snapshot",
    "clear_snapshot",
]
