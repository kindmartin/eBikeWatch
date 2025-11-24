"""Background thread helper that polls the Phaserunner controller."""

from time import sleep_ms, ticks_ms, ticks_diff

from machine import UART

from phaserunner import Phaserunner


def phaserunner_worker(
    state,
    *,
    stop_predicate,
    fast_interval_source,
    slow_interval_source,
    tx_pin,
    rx_pin,
):
    uart = UART(1, baudrate=115200, tx=tx_pin, rx=rx_pin, timeout=300)
    pr = Phaserunner(uart)
    next_fast = ticks_ms()
    next_slow = ticks_ms()
    slow_list = [
        ("vehicle_speed_PR", "vehicle_speed", "km/h"),
        ("controller_temp", "controller_temp", "?"),
        ("motor_temp", "motor_temp", "?"),
        ("motor_rpm", "motor_rpm", "rpm"),
        ("battery_voltage", "battery_voltage", "V"),
        ("throttle_voltage", "throttle_voltage", "V"),
        ("brake_voltage_1", "brake_voltage_1", "V"),
        ("digital_inputs", "digital_inputs", "?"),
        ("warnings", "warnings", ""),
    ]
    slow_idx = 0
    while not stop_predicate():
        now = ticks_ms()
        try:
            fast_ms = int(fast_interval_source())
        except Exception:
            fast_ms = fast_interval_source()
        try:
            slow_ms = int(slow_interval_source())
        except Exception:
            slow_ms = slow_interval_source()
        if fast_ms < 20:
            fast_ms = 20
        if slow_ms < fast_ms:
            slow_ms = fast_ms

        if ticks_diff(now, next_fast) >= 0:
            current_val = None
            power_val = None
            try:
                current_val = pr.read_value("battery_current")
                state.set_pr("battery_current", current_val, "A")
            except Exception:
                state.set_pr("battery_current", None, "A")
            try:
                power_val = pr.read_value("motor_input_power")
                state.set_pr("motor_input_power", power_val, "W")
            except Exception:
                state.set_pr("motor_input_power", None, "W")
            calc_v = None
            if power_val is not None and current_val not in (None, 0):
                try:
                    current_f = float(current_val)
                    power_f = float(power_val)
                    if abs(current_f) > 1e-3:
                        calc_v = power_f / current_f
                except Exception:
                    calc_v = None
            if calc_v is not None and calc_v == calc_v:
                state.set_pr("batt_voltage_calc", calc_v, "V")
            else:
                state.set_pr("batt_voltage_calc", None, "V")
            next_fast = ticks_ms() + fast_ms

        if ticks_diff(now, next_slow) >= 0:
            name, register, unit = slow_list[slow_idx]
            try:
                state.set_pr(name, pr.read_value(register), unit)
            except Exception:
                state.set_pr(name, None, unit)
            slow_idx = (slow_idx + 1) % len(slow_list)
            slow_step = slow_ms // len(slow_list)
            if slow_step < fast_ms:
                slow_step = fast_ms
            next_slow = ticks_ms() + slow_step

        sleep_ms(10)


__all__ = ["phaserunner_worker"]
