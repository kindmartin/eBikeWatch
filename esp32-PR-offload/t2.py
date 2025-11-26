"""Quick Phaserunner telemetry throughput test.

This script holds the throttle DAC at a fixed voltage and polls the
Phaserunner's fast registers (battery current and input power) as fast
as possible for a fixed duration. It prints per-second progress updates
and a final summary including the achieved sample rate and read latency.
"""

from time import sleep_ms, ticks_diff, ticks_ms, ticks_us

from machine import UART

from HW import PR_UART_RX, PR_UART_TX
from phaserunner import Phaserunner


REPORT_INTERVAL_MS = 1_000
SAMPLE_DELAY_MS = 500  # match testBatt pacing

# Copy of the working field list from testBatt.py (kept local to avoid modifying testBatt).
FIELDS = [
    "battery_current",
    "motor_input_power",
    "vehicle_speed",
    "controller_temp",
    "motor_temp",
    "motor_rpm",
    "battery_voltage",
    "throttle_voltage",
    "brake_voltage_1",
    "digital_inputs",
    "warnings",
]


def _format_status(elapsed_ms, stats):
    lines = ["[{:.1f}s]".format(elapsed_ms / 1000.0)]
    for name in FIELDS:
        reg_stats = stats[name]
        count = reg_stats["count"]
        errors = reg_stats["errors"]
        avg_us = (reg_stats["latency_us"] / count) if count else 0
        last_val = reg_stats["last"]
        samples_per_s = count / (elapsed_ms / 1000.0) if elapsed_ms else 0
        lines.append(
            "{}: {count} samp ({rate:.1f}/s) avg {avg:.2f} ms max {max:.2f} ms last {last} err {err}".format(
                name,
                count=count,
                rate=samples_per_s,
                avg=avg_us / 1000.0,
                max=reg_stats["latency_max_us"] / 1000.0,
                last="{:.3f}".format(last_val) if isinstance(last_val, (int, float)) else last_val,
                err=errors,
            )
        )
    return " | ".join(lines)


def _format_snapshot(snapshot):
    parts = []
    for name in FIELDS:
        value = snapshot.get(name)
        if value is None:
            parts.append("{}=--".format(name))
        elif name in ("digital_inputs", "warnings"):
            parts.append("{}={} (0x{:X})".format(name, int(value), int(value)))
        else:
            parts.append("{}={:.3f}".format(name, value))
    return " | ".join(parts)


def run(report_interval_ms=REPORT_INTERVAL_MS):
    uart = UART(1, baudrate=115200, tx=PR_UART_RX, rx=PR_UART_TX, timeout=300)
    pr = Phaserunner(uart)

    stats = {
        name: {
            "count": 0,
            "errors": 0,
            "latency_us": 0,
            "latency_max_us": 0,
            "last": None,
        }
        for name in FIELDS
    }
    snapshot = {name: None for name in FIELDS}

    start_ms = ticks_ms()
    last_report = start_ms

    try:
        while True:
            for name in FIELDS:
                begin = ticks_us()
                try:
                    value = pr.read_value(name)
                    snapshot[name] = value
                    stats[name]["count"] += 1
                    stats[name]["last"] = value
                    read_ok = True
                except Exception as exc:
                    snapshot[name] = None
                    stats[name]["errors"] += 1
                    stats[name]["last"] = exc
                    read_ok = False
                elapsed_us = ticks_diff(ticks_us(), begin)
                stats[name]["latency_us"] += elapsed_us
                if elapsed_us > stats[name]["latency_max_us"]:
                    stats[name]["latency_max_us"] = elapsed_us
                if not read_ok:
                    sleep_ms(5)

            now_ms = ticks_ms()
            if ticks_diff(now_ms, last_report) >= report_interval_ms:
                elapsed_ms = ticks_diff(now_ms, start_ms)
                print(_format_status(elapsed_ms, stats))
                print(_format_snapshot(snapshot))
                last_report = now_ms

            sleep_ms(SAMPLE_DELAY_MS)
    except KeyboardInterrupt:
        print("[t2] Interrupted by user")


run()




