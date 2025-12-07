"""Minimal helpers for preparing ESP32 deep sleep wake pins and VBUS state."""

try:  # pragma: no cover - MicroPython specific
    import esp32  # type: ignore
except ImportError:  # pragma: no cover - host tooling
    esp32 = None  # type: ignore

import machine  # type: ignore

__all__ = ["ensure_wake_pin_ready", "vbus_present"]


def vbus_present(state, min_vbus_v=4.2):
    """Return True when the runtime reports that VBUS is still available."""

    if state is None:
        return False
    power_status = getattr(state, "sys_power_status", {}) or {}
    board_source = getattr(state, "sys_board_source", "") or ""
    if board_source.upper() == "VBUS":
        return True
    if bool(power_status.get("vbus_present")):
        return True
    try:
        vbus_v = float(getattr(state, "sys_vbus_v", 0.0) or 0.0)
    except Exception:
        vbus_v = 0.0
    return vbus_v >= min_vbus_v


def ensure_wake_pin_ready(pin_num):
    """Configure the RTC wake pin ahead of deep sleep."""

    return _configure_wake_pin(pin_num)


def _configure_wake_pin(pin_num):
    wake_high = getattr(machine.Pin, "WAKE_HIGH", 1)
    pull_down = getattr(machine.Pin, "PULL_DOWN", None)
    pin = (
        machine.Pin(pin_num, machine.Pin.IN, pull_down)
        if pull_down is not None
        else machine.Pin(pin_num, machine.Pin.IN)
    )

    configured = False
    rtc_cls = getattr(machine, "RTC", None)
    if rtc_cls is not None:
        rtc = rtc_cls()
        wake_fn = getattr(rtc, "wake_on_ext0", None)
        if callable(wake_fn):
            wake_fn(pin=pin, level=wake_high)
            configured = True
            try:
                print("[power_guard] wake configured via RTC ext0 on GPIO{}".format(pin_num))
            except Exception:
                pass

    if not configured and esp32 is not None:
        wake_level = getattr(esp32, "WAKEUP_EXT0_HIGH", wake_high)
        esp32.wake_on_ext0(pin=pin, level=wake_level)
        configured = True
        try:
            print("[power_guard] wake configured via esp32.ext0 on GPIO{}".format(pin_num))
        except Exception:
            pass
    return configured
