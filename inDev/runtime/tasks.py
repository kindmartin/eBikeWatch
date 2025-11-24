"""Async task helpers for the eBikeWatch runtime."""

import sys
import uasyncio as asyncio
from time import ticks_ms, ticks_diff


async def ui_task(dashboards, state, interval_source):
    """Drive the active dashboard refresh loop."""
    minimum = 20
    while True:
        idx = state.screen if isinstance(state.screen, int) else 0
        if idx < 0 or idx >= len(dashboards):
            idx = 0
            state.screen = 0
        dashboard = dashboards[idx]
        try:
            dashboard.draw(state)
        except Exception as exc:  # pragma: no cover - defensive logging on device
            print("[UI] draw error:", exc)
            try:
                sys.print_exception(exc)
            except Exception:
                pass
            await asyncio.sleep_ms(200)
            continue
        try:
            interval_cfg = int(interval_source())
        except Exception:
            interval_cfg = interval_source()
        if interval_cfg < minimum:
            interval_cfg = minimum
        await asyncio.sleep_ms(interval_cfg)


async def integrator_task(state, interval_source):
    """Periodically integrate distance and energy counters."""
    minimum = 50
    while True:
        state.integrate()
        try:
            interval_cfg = int(interval_source())
        except Exception:
            interval_cfg = interval_source()
        if interval_cfg < minimum:
            interval_cfg = minimum
        await asyncio.sleep_ms(interval_cfg)


async def trip_counter_task(
    state,
    *,
    counter_id=0,
    pin_num=32,
    pulse_to_meter=0.1,
    edge=None,
    filter_ns=50_000,
    interval_ms=1000,
    interval_source=None,
):
    """Maintain trip counter values using the machine.Counter peripheral."""

    try:
        import machine
        Counter = getattr(machine, "Counter")
        Pin = machine.Pin
    except (ImportError, AttributeError):
        print("[Trip] Counter support unavailable")
        state.trip_counter_available = False
        state.trip_counter_error = "unsupported"
        return

    def _resolve_edge(value):
        if Counter is None:
            return value
        if value is None:
            return getattr(Counter, "RISING", 1)
        if isinstance(value, str):
            attr = getattr(Counter, value.upper(), None)
            if attr is not None:
                return attr
            try:
                return int(value)
            except Exception:
                return getattr(Counter, "RISING", 1)
        return value

    try:
        pin = Pin(int(pin_num), Pin.IN)
        counter_edge = _resolve_edge(edge)
        kwargs = {"edge": counter_edge}
        try:
            kwargs["filter_ns"] = int(filter_ns)
        except Exception:
            pass
        counter = Counter(int(counter_id), pin, **kwargs)
    except Exception as exc:
        msg = "{}".format(exc)
        print("[Trip] Counter init error:", msg)
        state.trip_counter_available = False
        state.trip_counter_error = msg
        return

    reset = getattr(counter, "reset", None)
    try:
        if callable(reset):
            reset()
        else:
            setter = getattr(counter, "value", None)
            if callable(setter):
                setter(0)
    except Exception:
        pass

    state.trip_counter_available = True
    state.trip_counter_error = ""
    state.trip_pulses = 0
    state.trip_distance_m = 0.0
    state.trip_distance_km = 0.0
    state.trip_speed_kmh = 0.0

    try:
        pulse_to_meter = float(pulse_to_meter or 0.0)
    except Exception:
        pulse_to_meter = 0.0
    try:
        sleep_ms = max(100, int(interval_ms or 1000))
    except Exception:
        sleep_ms = 1000

    last_speed_sample_ms = ticks_ms()
    last_speed_pulses = 0
    first_speed_sample = True

    def _read_counter_value():
        reader = getattr(counter, "count", None)
        if callable(reader):
            return reader()
        value_fn = getattr(counter, "value", None)
        if callable(value_fn):
            return value_fn()
        return getattr(counter, "value", 0)

    try:
        while True:
            try:
                raw = _read_counter_value()
                if isinstance(raw, int):
                    pulses = raw
                elif isinstance(raw, float):
                    pulses = int(raw)
                elif isinstance(raw, str):
                    try:
                        pulses = int(raw)
                    except Exception:
                        pulses = 0
                else:
                    pulses = 0
            except Exception as exc:
                msg = "{}".format(exc)
                if state.trip_counter_available:
                    print("[Trip] Counter read error:", msg)
                state.trip_counter_available = False
                state.trip_counter_error = msg
                return

            state.trip_pulses = pulses
            distance_m = pulses * pulse_to_meter
            state.trip_distance_m = distance_m
            state.trip_distance_km = distance_m / 1000.0 if pulse_to_meter else 0.0

            now_ms = ticks_ms()
            if first_speed_sample:
                first_speed_sample = False
                last_speed_sample_ms = now_ms
                last_speed_pulses = pulses
                state.trip_speed_kmh = 0.0
            else:
                elapsed_ms = ticks_diff(now_ms, last_speed_sample_ms)
                if elapsed_ms < 0:
                    first_speed_sample = True
                    state.trip_speed_kmh = 0.0
                elif elapsed_ms >= 1000:
                    delta_pulses = pulses - last_speed_pulses
                    if delta_pulses < 0:
                        last_speed_sample_ms = now_ms
                        last_speed_pulses = pulses
                        state.trip_speed_kmh = 0.0
                    elif pulse_to_meter > 0 and elapsed_ms > 0:
                        meters_delta = delta_pulses * pulse_to_meter
                        speed_m_per_s = meters_delta / (elapsed_ms / 1000.0)
                        if speed_m_per_s < 0:
                            speed_m_per_s = 0.0
                        state.trip_speed_kmh = speed_m_per_s * 3.6
                        last_speed_sample_ms = now_ms
                        last_speed_pulses = pulses

            state.trip_counter_available = True
            state.trip_counter_error = ""

            sleep_value = sleep_ms
            if callable(interval_source):
                try:
                    candidate = int(interval_source())
                    if candidate >= 100:
                        sleep_ms = candidate
                        sleep_value = candidate
                except Exception:
                    pass
            await asyncio.sleep_ms(sleep_value)
    except asyncio.CancelledError:
        raise
    finally:
        state.trip_counter_available = False
        state.trip_counter_error = ""
        state.trip_speed_kmh = 0.0


async def heartbeat_task(state):
    """Optional console heartbeat for debugging."""
    n = 0
    while True:
        speed_fn = getattr(state, "vehicle_speed", None)
        if callable(speed_fn):
            try:
                speed_val = speed_fn()
            except Exception:
                speed_val = None
            if isinstance(speed_val, (int, float)):
                vs = speed_val
            elif speed_val is None:
                vs = 0.0
            else:
                vs = 0.0
        else:
            vs = state.get_pr("vehicle_speed", (0.0, ""))[0] or 0.0
        pin = state.get_pr("motor_input_power", (0.0, ""))[0] or 0.0
        print(
            "[HB]",
            n,
            "spd={:.1f} P={:.0f} scr={} km={:.2f} wh={:.2f}".format(
                vs,
                pin,
                state.screen,
                state.km_total,
                state.wh_total,
            ),
        )
        n += 1
        await asyncio.sleep(3)


__all__ = [
    "ui_task",
    "integrator_task",
    "trip_counter_task",
    "heartbeat_task",
]
