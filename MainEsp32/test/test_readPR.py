"""Quick Phaserunner telemetry throughput test.

This script holds the throttle DAC at a fixed voltage and polls the
Phaserunner's fast registers (battery current and input power) as fast
as possible for a fixed duration. It prints per-second progress updates
and a final summary including the achieved sample rate and read latency.
"""

from time import sleep_ms, ticks_diff, ticks_ms, ticks_us

from machine import UART

from HW import (
    DAC0_ADDR,
    PR_UART_RX,
    PR_UART_TX,
    dacs_zero_both,
    make_i2c,
    set_dac_volts,
)
from phaserunner.phaserunner import Phaserunner


TEST_DURATION_MS = 10_000
THROTTLE_VOLTS = 2.0
REPORT_INTERVAL_MS = 1_000
FAST_REGISTERS = ("battery_current", "motor_input_power")


def _format_status(elapsed_ms, stats):
    lines = ["[{:.1f}s]".format(elapsed_ms / 1000.0)]
    for name in FAST_REGISTERS:
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
                last="{:.2f}".format(last_val) if isinstance(last_val, (int, float)) else last_val,
                err=errors,
            )
        )
    return " | ".join(lines)


def run(duration_ms=TEST_DURATION_MS, throttle_volts=THROTTLE_VOLTS, report_interval_ms=REPORT_INTERVAL_MS):
    i2c = make_i2c()
    uart = UART(1, baudrate=115200, tx=PR_UART_TX, rx=PR_UART_RX, timeout=300)
    pr = Phaserunner(uart)

    stats = {
        name: {
            "count": 0,
            "errors": 0,
            "latency_us": 0,
            "latency_max_us": 0,
            "last": None,
        }
        for name in FAST_REGISTERS
    }

    dacs_zero_both(i2c)
    print("[test_readPR] DACs zeroed. Starting in 1 second...")
    sleep_ms(1000)

    print(
        "[test_readPR] Holding throttle DAC at {:.2f} V for {:.1f} seconds".format(
            throttle_volts, duration_ms / 1000.0
        )
    )
    set_dac_volts(i2c, DAC0_ADDR, throttle_volts)

    start_ms = ticks_ms()
    last_report = start_ms

    try:
        while ticks_diff(ticks_ms(), start_ms) < duration_ms:
            for name in FAST_REGISTERS:
                begin = ticks_us()
                try:
                    value = pr.read_value(name)
                    stats[name]["count"] += 1
                    stats[name]["last"] = value
                    read_ok = True
                except Exception as exc:
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
                last_report = now_ms

            sleep_ms(0)
    except KeyboardInterrupt:
        print("[test_readPR] Interrupted by user")
    finally:
        dacs_zero_both(i2c)
        print("[test_readPR] DACs returned to 0 V")

    total_elapsed_ms = ticks_diff(ticks_ms(), start_ms)
    print("[test_readPR] Test complete")
    print(_format_status(total_elapsed_ms, stats))


def main():
    run()


if __name__ == "__main__":
    main()