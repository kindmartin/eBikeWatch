"""Wheel pulse calibration helper.

Run this script to compare Phaserunner speed against the wheel pulse counter
while keeping the throttle DAC at a fixed reference voltage. The delta
between both readings can be used to refine the ``trip_pulse_to_meter``
configuration entry.

Usage (from the MicroPython REPL)::

    import trip_calibration
    trip_calibration.run(duration_sec=120, throttle_volts=2.0)

The loop prints once per second by default and stops automatically when the
optional ``duration_sec`` elapses (0 keeps it running until interrupted).
"""

import uasyncio as asyncio
from time import ticks_diff, ticks_ms

try:
    import ujson as json
except ImportError:  # CPython fallback for host-side dry runs
    import json

import HW
from phaserunner import pr_uart
from phaserunner.phaserunner import Phaserunner

CONFIG_FILE = "motor_config.json"


def _load_config():
    cfg = {}
    try:
        with open(CONFIG_FILE, "r") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception as exc:
        print("[cal] config load error:", exc)
    return cfg


def _prepare_throttle(cfg, throttle_volts):
    try:
        i2c = HW.make_i2c()
    except Exception as exc:
        print("[cal] I2C init error:", exc)
        return

    vref = cfg.get("dac_vref", 3.3)
    try:
        vref = float(vref)
    except Exception:
        vref = 3.3

    try:
        HW.set_dac_volts(i2c, HW.DAC0_ADDR, float(throttle_volts), vref)
        HW.set_dac_volts(i2c, HW.DAC1_ADDR, 0.0, vref)
        print("[cal] DAC throttle={:.2f}V brake=0.00V (vref {:.2f}V)".format(throttle_volts, vref))
    except Exception as exc:
        print("[cal] DAC set error:", exc)


def _resolve_edge(counter_cls, value):
    if value is None:
        return getattr(counter_cls, "RISING", 1)
    if isinstance(value, str):
        attr = getattr(counter_cls, value.upper(), None)
        if attr is not None:
            return attr
        try:
            return int(value)
        except Exception:
            return getattr(counter_cls, "RISING", 1)
    return value


def _create_counter(cfg):
    try:
        import machine
        Counter = getattr(machine, "Counter")
        Pin = machine.Pin
    except (ImportError, AttributeError) as exc:
        print("[cal] Counter unsupported:", exc)
        return None

    counter_id = cfg.get("trip_counter_id", HW.TRIP_COUNTER_ID)
    pin_num = cfg.get("trip_counter_pin", HW.TRIP_COUNTER_PIN)
    edge = cfg.get("trip_counter_edge", HW.TRIP_COUNTER_EDGE)
    filter_ns = cfg.get("trip_counter_filter_ns", HW.TRIP_COUNTER_FILTER_NS)

    try:
        counter_id = int(counter_id)
    except Exception:
        counter_id = HW.TRIP_COUNTER_ID
    try:
        pin_num = int(pin_num)
    except Exception:
        pin_num = HW.TRIP_COUNTER_PIN
    try:
        filter_ns = int(filter_ns)
    except Exception:
        filter_ns = HW.TRIP_COUNTER_FILTER_NS

    kwargs = {"edge": _resolve_edge(Counter, edge)}
    if filter_ns:
        kwargs["filter_ns"] = filter_ns

    try:
        counter = Counter(counter_id, Pin(pin_num, Pin.IN), **kwargs)
    except Exception as exc:
        print("[cal] Counter init error:", exc)
        return None

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

    print("[cal] Counter ready on pin {} (id {})".format(pin_num, counter_id))
    return counter


def _read_counter(counter):
    reader = getattr(counter, "count", None)
    if callable(reader):
        return reader() or 0
    value_fn = getattr(counter, "value", None)
    if callable(value_fn):
        return value_fn() or 0
    value = getattr(counter, "value", 0)
    return value or 0


async def _calibration_loop(pr, counter, pulse_to_meter, interval_ms, duration_sec):
    try:
        pulse_to_meter = float(pulse_to_meter or 0.0)
    except Exception:
        pulse_to_meter = 0.0
    interval_ms = max(200, int(interval_ms))
    duration_ms = int(duration_sec * 1000) if duration_sec else 0

    last_count = _read_counter(counter)
    last_ms = ticks_ms()
    start_ms = last_ms

    print("[cal] Using pulse_to_meter={:.6f} ({} m per pulse)".format(pulse_to_meter, pulse_to_meter))
    print("[cal] Sampling every {} ms".format(interval_ms))

    while True:
        await asyncio.sleep_ms(interval_ms)
        now = ticks_ms()
        current = _read_counter(counter)
        delta_pulses = current - last_count
        if delta_pulses < 0:
            delta_pulses = 0
        dt_ms = ticks_diff(now, last_ms)
        if dt_ms <= 0:
            dt_ms = interval_ms

        last_count = current
        last_ms = now

        wheel_kmh = 0.0
        est_factor = None
        if dt_ms > 0 and pulse_to_meter > 0:
            wheel_kmh = (delta_pulses * pulse_to_meter * 3600.0) / dt_ms

        try:
            pr_speed = pr.read_value("vehicle_speed")
        except Exception as exc:
            pr_speed = None
            print("[cal] Phaserunner read error:", exc)
        ratio = None
        if pr_speed is not None and pr_speed > 0 and delta_pulses > 0 and dt_ms > 0:
            ratio = wheel_kmh / pr_speed if pr_speed else None
            # Estimate metres per pulse based on Phaserunner reading
            speed_mps = pr_speed / 3.6
            est_factor = (speed_mps * (dt_ms / 1000.0)) / delta_pulses

        if pr_speed is None:
            pr_display = "n/a"
        else:
            pr_display = "{:.2f}".format(pr_speed)
        ratio_display = "{:.3f}".format(ratio) if ratio is not None else "n/a"
        factor_display = "{:.5f}".format(est_factor) if est_factor is not None else "n/a"

        print("[cal] Δp={:4d} wheel={:6.2f}km/h pr={:>6}km/h ratio={} est_factor={}".format(
            delta_pulses,
            wheel_kmh,
            pr_display,
            ratio_display,
            factor_display,
        ))

        if duration_ms and ticks_diff(now, start_ms) >= duration_ms:
            print("[cal] Duration reached ({} s).".format(duration_sec))
            break


async def _async_main(duration_sec, interval_ms, throttle_volts, mapping):
    cfg = _load_config()
    pulse_to_meter = cfg.get("trip_pulse_to_meter", 0.1)
    _prepare_throttle(cfg, throttle_volts)
    counter = _create_counter(cfg)
    if counter is None:
        return

    if mapping is None:
        print("[cal] Probing Phaserunner UART mapping...")
        try:
            probe = await pr_uart.quick_probe(seconds=2, register="vehicle_speed")
        except Exception as exc:
            print("[cal] UART probe error:", exc)
            probe = None
        mapping = probe[0] if probe else "A"
    uart, tx_pin, rx_pin = pr_uart.make_uart(mapping, timeout=200, timeout_char=2)
    print("[cal] Using UART mapping {} (TX={}, RX={})".format(mapping, tx_pin, rx_pin))
    pr = Phaserunner(uart)

    try:
        await _calibration_loop(pr, counter, pulse_to_meter, interval_ms, duration_sec)
    finally:
        try:
            uart.deinit()
        except Exception:
            pass


def run(*, duration_sec=0, interval_ms=1000, throttle_volts=2.0, mapping=None):
    """Entry point for the calibration helper.

    :param duration_sec: Run time in seconds (0 keeps it running).
    :param interval_ms: Sampling interval in milliseconds.
    :param throttle_volts: Throttle DAC voltage to apply before sampling.
    :param mapping: Optional Phaserunner UART mapping ('A' or 'B').
    """

    try:
        asyncio.run(_async_main(duration_sec, interval_ms, throttle_volts, mapping))
    except KeyboardInterrupt:
        print("[cal] Interrupted.")