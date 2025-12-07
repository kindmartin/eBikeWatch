# t.py
# PR en hilo dedicado + UI/botones en uasyncio.
# Cambios:
# - API de consola:
#     import t; t.print_status()
import _thread
import uasyncio as asyncio
from time import sleep_ms, ticks_ms, ticks_diff, ticks_add
import sys
import machine  # type: ignore

try:
    import ujson as json  # type: ignore
except ImportError:  # pragma: no cover
    import json

import bats

from HW import (
    PAGE_BTN_PIN,
    UPDOWN_ADC_PIN,
    ADC_THROTTLE_PIN,
    ADC_BRAKE_PIN,
    PR_UART_ID,
    PR_UART_TX,
    PR_UART_RX,
    PR_UART_BAUD,
    TRIP_COUNTER_ID,
    TRIP_COUNTER_PIN,
    TRIP_COUNTER_FILTER_NS,
    TRIP_COUNTER_EDGE,
    TRIP_COUNTER_INTERVAL_MS,
    PR_OFFLOAD_WAKE_PIN,
    MAIN_WAKE_PIN,
    make_i2c,
    make_adc,
    make_input,
    make_output,
)

from UI_helpers import DisplayUI
from app_state import AppState
import buttons as _buttons_mod
from buttons import PageButton, UpDownButtons
from runtime.motor import (
    MOTOR_CONFIG_FILE,
    MOTOR_DEFAULTS,
    compute_output_voltages,
    create_motor_control,
    load_motor_config,
    save_motor_config,
)
from runtime.tasks import ui_task, integrator_task, trip_counter_task, heartbeat_task
from runtime.sys_pmu import sys_pmu_task
from runtime.power_guard import ensure_wake_pin_ready, vbus_present
from runtime.rtc_snapshot import save_trip_snapshot, restore_trip_snapshot
from runtime.ui_manager import (
    DashboardInputRouter,
    ThrottleModeController,
    create_dashboards,
    load_dashboard_order,
)
from runtime.status_display import show_status_screen as _show_status_screen

try:
    from runtime.tasks import gc_task  # type: ignore[attr-defined]
except ImportError:
    async def gc_task(config_source):  # type: ignore[return-type]
        """Fallback GC task when runtime.tasks lacks gc_task (older firmware)."""
        import uasyncio as _asyncio

        minimum = 1000
        print("[t] warning: runtime.tasks.gc_task missing; using no-op stub")
        while True:
            try:
                cfg = config_source() or {}
            except Exception:
                cfg = {}
            try:
                interval_ms = int(cfg.get("interval_ms", 60000))
            except Exception:
                interval_ms = 60000
            if interval_ms < minimum:
                interval_ms = minimum
            await _asyncio.sleep_ms(interval_ms)
import runtime.phaserunner_worker as pr_bridge
from runtime.hardware import init_dacs_zero

try:
    from version import APP_VERSION, module_version
except ImportError:  # pragma: no cover
    APP_VERSION = "0.0.0"

    def module_version(name, default=None):
        return default if default is not None else APP_VERSION

__version__ = module_version("t")


AUTO_START = True
DEBUG = False   # <-- por defecto NO imprime nada
_HB_TASK = None # handler del heartbeat si se activa
_dashboards = []
_dashboard_signals = None
_dashboard_trip = None
_dashboard_batt_select = None
_dashboard_batt_status = None
_dashboard_sys_batt = None
_dashboard_alarm = None
_page_button = None
_motor = None
_updown_buttons = None
_TASKS = []
_STOP_REQUESTED = False
_RUNNING = False
_PR_THREAD_ACTIVE = False
_PR_THREAD_ENABLED = True  # enable PR bridge thread by default
_PR_THREAD_STACK = 6144
_PR_THREAD_STOP_REQUESTED = False
_BG_THREAD_STACK = 12288
_CONTROL_LOOP_DEBUG_OVERRIDE = None
_CONTROL_LOOP_DEBUG_PERIOD_MS = None
_LOOP_TIMING_MONITOR_OVERRIDE = None
_PID_TIMING_DEBUG_OVERRIDE = None
_PID_TIMING_DEBUG_PERIOD_MS = None

_UART_RELEASE_QUEUE = []
_UART_RELEASE_LOCK = _thread.allocate_lock()
_PR_WAKE_PIN = None

_GC_TASK_ENABLED = True
_GC_INTERVAL_MS = 120000
_GC_VERBOSE = False

_PID_PARAM_SUFFIXES = {
    "kp": "kp",
    "ki": "ki",
    "kd": "kd",
    "integral_limit": "integral_limit",
    "i_limit": "integral_limit",
    "limit": "integral_limit",
    "d_alpha": "d_alpha",
    "dalpha": "d_alpha",
    "derivative_alpha": "d_alpha",
    "output_alpha": "output_alpha",
    "alpha": "output_alpha",
}
_PID_PARAM_GUIDANCE = {
    "kp": "Raise to reduce steady error; lower if you see oscillation/overshoot.",
    "ki": "Integrates bias; increase for sagging response, decrease if it slowly ramps past target.",
    "kd": "Damps fast changes; add when the monitor shows repeated overshoot despite low Kp.",
    "integral_limit": "Caps the I term; trim down if recovery is sluggish after braking.",
    "d_alpha": "Smoothing for the derivative; higher=slower filter (less noise, more lag).",
    "output_alpha": "Low-pass on controller output; reduce for faster reaction, raise to calm DAC jitter.",
}


_SLEEP_GUARD_LOG_BUCKET_MS = 1000


async def _enter_sleep_sequence(state, wake_pin):
    print("[t] sleep guard: initiating shutdown sequence")
    if _ui is not None:
        _show_status_screen(_ui, "Shutting down...", state)
    try:
        pr_offload_allow_sleep()
        print("[t] sleep guard: PR-offload wake line (GPIO{}) forced LOW".format(PR_OFFLOAD_WAKE_PIN))
    except Exception as exc:
        print("[t] sleep guard: unable to pull PR wake line LOW", exc)

    try:
        sleep_ack = pr_offload_sleep(wait_ms=1000, delay_s=2)
        print("[t] sleep guard: PR-offload sleep command ->", sleep_ack)
    except Exception as exc:
        print("[t] sleep guard: PR-offload sleep command failed", exc)

    if save_trip_snapshot(state):
        print("[t] sleep guard: RTC trip snapshot stored")
    else:
        print("[t] sleep guard: RTC trip snapshot failed")

    await asyncio.sleep_ms(100)

    try:
        if ensure_wake_pin_ready(wake_pin):
            print("[t] sleep guard: wake pin GPIO{} armed".format(wake_pin))
    except Exception as exc:
        print("[t] sleep guard: wake pin arm failed", exc)

    await asyncio.sleep_ms(200)
    print("[t] sleep guard: entering deep sleep")
    machine.deepsleep()


async def _sleep_guard_task(state, wake_pin, *, drop_ms=3_000, poll_ms=250, min_vbus_v=4.2):
    poll_ms = max(100, int(poll_ms))
    drop_ms = max(poll_ms, int(drop_ms))
    drop_start = None
    last_bucket = -1
    print(
        "[t] sleep guard: watching VBUS (GPIO{} wake, timeout {} ms)".format(
            wake_pin,
            drop_ms,
        )
    )
    while not _STOP_REQUESTED:
        await asyncio.sleep_ms(poll_ms)
        if state is None or not getattr(state, "sys_batt_last_update_ms", 0):
            drop_start = None
            last_bucket = -1
            continue
        if vbus_present(state, min_vbus_v=min_vbus_v):
            if drop_start is not None:
                print("[t] sleep guard: VBUS restored; timer cancelled")
            drop_start = None
            last_bucket = -1
            continue
        now = ticks_ms()
        if drop_start is None:
            drop_start = now
            last_bucket = -1
            print("[t] sleep guard: VBUS missing; 3 s countdown started")
            continue
        elapsed = ticks_diff(now, drop_start)
        if elapsed < 0:
            drop_start = now
            last_bucket = -1
            continue
        if elapsed < drop_ms:
            bucket = int(elapsed // _SLEEP_GUARD_LOG_BUCKET_MS)
            if bucket != last_bucket:
                last_bucket = bucket
                remaining = drop_ms - elapsed
                if remaining < 0:
                    remaining = 0
                print(
                    "[t] sleep guard: VBUS absent {:.0f} ms; {} ms remaining".format(
                        elapsed,
                        remaining,
                    )
                )
            continue
        await _enter_sleep_sequence(state, wake_pin)
        return


def schedule_sleep_guard(state, wake_pin, *, timeout_ms=3_000, poll_ms=250):
    try:
        wake_pin = int(wake_pin)
    except Exception:
        wake_pin = None
    if wake_pin is None or wake_pin < 0:
        print("[t] sleep guard: wake pin invalid; skipping")
        return
    try:
        task = asyncio.create_task(
            _sleep_guard_task(
                state,
                wake_pin,
                drop_ms=timeout_ms,
                poll_ms=poll_ms,
            )
        )
        _track_task(task)
        print(
            "[t] _main_async: sleep guard scheduled (GPIO{} / timeout {} ms)".format(
                wake_pin,
                timeout_ms,
            )
        )
    except Exception as exc:
        print("[t] sleep guard start error", exc)


async def auto_wake_pr_offload():
    await asyncio.sleep_ms(200)
    if not _PR_THREAD_ENABLED:
        return
    try:
        pr_offload_wake()
        print("[t] PR-offload wake pulse sent")
    except Exception as exc:
        print("[t] PR-offload wake skipped", exc)


def _read_wake_reason_code():
    wake_reason = getattr(machine, "wake_reason", None)
    if not callable(wake_reason):
        return None
    try:
        reason = wake_reason()
    except Exception:
        return None
    if isinstance(reason, tuple):  # ESP32 may return (reason, gpio)
        return reason[0] if reason else None
    return reason


def _woke_from_main_wake_pin():
    try:
        reset_cause = machine.reset_cause()
    except Exception:
        return False
    deep_const = getattr(machine, "DEEPSLEEP_RESET", None)
    if deep_const is not None and reset_cause != deep_const:
        return False
    reason_code = _read_wake_reason_code()
    if reason_code is None:
        return False
    ext0_aliases = (
        getattr(machine, "WAKE_EXT0", None),
        getattr(machine, "WAKEUP_EXT0", None),
        getattr(machine, "EXT0_WAKE", None),
    )
    return any(reason_code == alias for alias in ext0_aliases if alias is not None)

_PR_FAST_MS = 100
_PR_SLOW_MS = 2000
_UI_FRAME_MS = 80
_INTEGRATOR_MS = 200
_TRIP_COUNTER_INTERVAL_MS = TRIP_COUNTER_INTERVAL_MS


def _track_task(task):
    if task is None:
        return None
    try:
        _TASKS.append(task)
    except Exception:
        pass
    return task


def _wait_for_pr_thread_idle(timeout_ms):
    if timeout_ms is None or timeout_ms <= 0:
        return not _PR_THREAD_ACTIVE
    try:
        remaining = int(timeout_ms)
    except Exception:
        remaining = 0
    while _PR_THREAD_ACTIVE and remaining > 0:
        sleep_ms(20)
        remaining -= 20
    return not _PR_THREAD_ACTIVE


def _blocking_release_pr_uart(
    *,
    release_delay_ms=200,
    stop_thread_wait_ms=500,
    idle_timeout_ms=1200,
    post_release_delay_ms=100,
):
    if release_delay_ms and release_delay_ms > 0:
        try:
            sleep_ms(int(release_delay_ms))
        except Exception:
            pass
    try:
        stop_pr_thread(wait_ms=int(stop_thread_wait_ms or 0))
    except Exception as exc:
        print("[t] UART release: stop thread error", exc)
    wait_ms = idle_timeout_ms if idle_timeout_ms and idle_timeout_ms > 0 else stop_thread_wait_ms
    if wait_ms is None or wait_ms <= 0:
        wait_ms = 500
    deadline = ticks_add(ticks_ms(), int(wait_ms))
    while _PR_THREAD_ACTIVE and ticks_diff(deadline, ticks_ms()) > 0:
        sleep_ms(20)
    try:
        if release_pr_uart_lines():
            print("[t] PR UART pins released")
        else:
            print("[t] PR UART release skipped (busy)")
    except Exception as exc:
        print("[t] UART release: release error", exc)
    if post_release_delay_ms and post_release_delay_ms > 0:
        try:
            sleep_ms(int(post_release_delay_ms))
        except Exception:
            pass


def _queue_uart_release(**kwargs):
    _UART_RELEASE_LOCK.acquire()
    try:
        _UART_RELEASE_QUEUE.append(dict(kwargs))
        return True
    finally:
        _UART_RELEASE_LOCK.release()


async def _uart_release_worker():
    while not _STOP_REQUESTED:
        params = None
        try:
            if not _UART_RELEASE_LOCK.acquire(0):
                await asyncio.sleep_ms(50)
                continue
        except AttributeError:
            await asyncio.sleep_ms(50)
            continue
        try:
            if _UART_RELEASE_QUEUE:
                params = _UART_RELEASE_QUEUE.pop(0)
        finally:
            _UART_RELEASE_LOCK.release()
        if params is None:
            await asyncio.sleep_ms(50)
            continue
        try:
            _blocking_release_pr_uart(**params)
        except Exception as exc:
            print("[t] UART release worker exception", exc)


async def _cancel_tracked_tasks():
    global _HB_TASK
    tasks = list(_TASKS)
    _TASKS.clear()
    for task in tasks:
        try:
            task.cancel()
        except Exception:
            pass
    if _HB_TASK is not None:
        try:
            _HB_TASK.cancel()
        except Exception:
            pass
        _HB_TASK = None
    for task in tasks:
        try:
            await task
        except Exception:
            pass


def is_running():
    return _RUNNING


def stop(wait_ms=0):
    global _STOP_REQUESTED
    if not _RUNNING:
        print("[t] stop: app not running")
        return False
    print("[t] stop: requesting shutdown")
    _STOP_REQUESTED = True
    if wait_ms:
        remaining = int(wait_ms)
        while (_RUNNING or _PR_THREAD_ACTIVE) and remaining > 0:
            sleep_ms(10)
            remaining -= 10
    return True


def _load_motor_config():
    return load_motor_config()


def _save_motor_config(cfg):
    return save_motor_config(cfg)


def _create_motor_control(cfg):
    return create_motor_control(cfg, config_file=MOTOR_CONFIG_FILE)


def _stop_predicate():
    return _STOP_REQUESTED or _PR_THREAD_STOP_REQUESTED


def _get_pr_fast_interval():
    return _PR_FAST_MS


def _get_pr_slow_interval():
    return _PR_SLOW_MS


def _get_ui_frame_interval():
    return _UI_FRAME_MS


def _get_integrator_interval():
    return _INTEGRATOR_MS


def _get_trip_counter_interval():
    return _TRIP_COUNTER_INTERVAL_MS


def _get_gc_interval():
    return _GC_INTERVAL_MS


def _gc_task_config():
    return {
        "enabled": _GC_TASK_ENABLED,
        "interval_ms": _GC_INTERVAL_MS,
        "verbose": _GC_VERBOSE,
    }


def _pr_worker_thread():
    global _PR_THREAD_ACTIVE, _PR_THREAD_STOP_REQUESTED
    if _state is None:
        return
    if not _PR_THREAD_ENABLED:
        return
    _PR_THREAD_ACTIVE = True
    try:
        pr_bridge.phaserunner_worker(
            _state,
            stop_predicate=_stop_predicate,
            fast_interval_source=_get_pr_fast_interval,
            slow_interval_source=_get_pr_slow_interval,
        )
    finally:
        _PR_THREAD_ACTIVE = False
        _PR_THREAD_STOP_REQUESTED = False


def _start_pr_thread():
    if _state is None:
        print("[PR] start skipped: state not ready")
        return
    if not _PR_THREAD_ENABLED:
        print("[PR] start skipped: disabled")
        return
    if _PR_THREAD_ACTIVE:
        return
    try:
        global _PR_THREAD_STOP_REQUESTED
        _PR_THREAD_STOP_REQUESTED = False
        if _PR_THREAD_STACK:
            try:
                _thread.stack_size(int(_PR_THREAD_STACK))
            except Exception as exc:
                print("[PR] stack size set error:", exc)
        _thread.start_new_thread(_pr_worker_thread, ())
    except Exception as exc:
        print("[PR] thread start error:", exc)


def set_pr_thread(enabled=True):
    global _PR_THREAD_ENABLED
    try:
        flag = bool(enabled)
    except Exception:
        flag = True
    _PR_THREAD_ENABLED = flag
    state = "enabled" if flag else "disabled"
    print("[t] Phaserunner thread {}".format(state))
    if flag:
        if not _PR_THREAD_ACTIVE:
            _start_pr_thread()
    else:
        stop_pr_thread(wait_ms=0)
    return flag


def set_pr_thread_stack(bytes_size=None):
    global _PR_THREAD_STACK
    if bytes_size is None:
        return int(_PR_THREAD_STACK)
    try:
        value = int(bytes_size)
    except Exception:
        raise ValueError("invalid stack size")
    if value < 2048:
        value = 2048
    _PR_THREAD_STACK = value
    print("[t] Phaserunner thread stack -> {} bytes".format(value))
    return value


def stop_pr_thread(wait_ms=0, disable=False):
    global _PR_THREAD_STOP_REQUESTED, _PR_THREAD_ENABLED
    if disable:
        _PR_THREAD_ENABLED = False
    if not _PR_THREAD_ACTIVE:
        _PR_THREAD_STOP_REQUESTED = False
        if not disable:
            print("[t] Phaserunner thread already stopped")
        return False
    print("[t] Phaserunner thread stop requested")
    _PR_THREAD_STOP_REQUESTED = True
    if wait_ms:
        remaining = int(wait_ms)
        while _PR_THREAD_ACTIVE and remaining > 0:
            sleep_ms(10)
            remaining -= 10
    return True


def start_pr_thread(force=False):
    global _PR_THREAD_ENABLED
    if _PR_THREAD_ACTIVE and not force:
        print("[t] Phaserunner thread already running")
        return False
    if force and _PR_THREAD_ACTIVE:
        stop_pr_thread(wait_ms=500)
        if _PR_THREAD_ACTIVE:
            print("[t] Phaserunner thread still stopping; retry soon")
            return False
    _PR_THREAD_ENABLED = True
    _start_pr_thread()
    return True


def set_bg_thread_stack(bytes_size=None):
    global _BG_THREAD_STACK
    if bytes_size is None:
        return int(_BG_THREAD_STACK)
    try:
        value = int(bytes_size)
    except Exception:
        raise ValueError("invalid stack size")
    if value < 4096:
        value = 4096
    _BG_THREAD_STACK = value
    print("[t] background thread stack -> {} bytes".format(value))
    return value


# -------------- API pública on-demand --------------
_state = None
_ui = None


def get_version():
    """Return the runtime module version string."""
    return __version__


def print_status():
    """Imprime un snapshot único del estado actual (on-demand)."""
    if _state is None:
        print("t: aún no inicializado")
        return
    st = _state
    snap = st.snapshot_pr()
    mins = int(ticks_diff(ticks_ms(), st.boot_ms) / 60000)
    speed_fn = getattr(st, "vehicle_speed", None)
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
        vs = snap.get("vehicle_speed", (0, ""))[0] or 0
        if not vs:
            vs = snap.get("vehicle_speed_PR", (0, ""))[0] or 0
    bv = snap.get("battery_voltage", (0, ""))[0] or 0
    bc = snap.get("battery_current", (0, ""))[0] or 0
    pin = snap.get("motor_input_power", (bv * bc, ""))[0] or (bv * bc)
    tv = getattr(st, "throttle_v", 0.0) or 0.0
    br = getattr(st, "brake_v", 0.0) or 0.0
    dtr = getattr(st, "dac_throttle_v", 0.0) or 0.0
    dbr = getattr(st, "dac_brake_v", 0.0) or 0.0
    pulses = getattr(st, "trip_pulses", 0) or 0
    trip_km = getattr(st, "trip_distance_km", None)
    if trip_km is None:
        trip_km = (getattr(st, "trip_distance_m", 0.0) or 0.0) / 1000.0
    trip_speed = getattr(st, "trip_speed_kmh", 0.0) or 0.0
    print(
        "[STATUS] t={}m spd={:.1f}km/h V={:.1f} I={:.1f} P={:.0f}W km={:.2f} Wh={:.2f} TH={:.2f}/{:.2f} BR={:.2f}/{:.2f} TR={}p DS={:.3f}km TS={:.1f}km/h".format(
            mins,
            vs,
            bv,
            bc,
            pin,
            st.km_total,
            st.wh_total,
            tv,
            dtr,
            br,
            dbr,
            pulses,
            trip_km,
            trip_speed,
        )
    )


def get_pr_intervals():
    """Return (fast_ms, slow_ms) used by the Phaserunner polling thread."""
    return int(_PR_FAST_MS), int(_PR_SLOW_MS)


def set_pr_fast_interval(ms=None, *, wait_ms=1000):
    """Set or query Phaserunner fast polling period (ms)."""
    global _PR_FAST_MS
    if ms is None:
        return int(_PR_FAST_MS)
    try:
        value = int(ms)
    except Exception:
        raise ValueError("invalid fast interval")
    if value < 20:
        value = 20
    resp = pr_bridge.send_command({"cmd": "set_fast", "ms": value}, wait_ms=wait_ms)
    if not resp or not resp.get("ok"):
        raise RuntimeError("set_fast failed: {}".format(resp))
    applied = int(resp.get("fast_ms", value))
    _PR_FAST_MS = applied
    return applied


def set_pr_slow_interval(ms=None, *, wait_ms=1000):
    """Set or query Phaserunner slow polling cycle length (ms)."""
    global _PR_SLOW_MS
    if ms is None:
        return int(_PR_SLOW_MS)
    try:
        value = int(ms)
    except Exception:
        raise ValueError("invalid slow interval")
    if value < 100:
        value = 100
    if value < _PR_FAST_MS:
        value = _PR_FAST_MS
    resp = pr_bridge.send_command({"cmd": "set_slow", "ms": value}, wait_ms=wait_ms)
    if not resp or not resp.get("ok"):
        raise RuntimeError("set_slow failed: {}".format(resp))
    applied = int(resp.get("slow_ms", value))
    _PR_SLOW_MS = applied
    return applied


def pr_bridge_status():
    """Return UART bridge diagnostics (rx counters, last seq/timestamp)."""
    return pr_bridge.get_bridge_status()


def pr_bridge_latest_payload():
    """Return the most recent raw telemetry frame from the PR-offload MCU."""
    return pr_bridge.get_latest_payload()


def pr_bridge_errors():
    """Return the last per-register error map reported by the offload MCU."""
    return pr_bridge.get_last_errors()


def pr_ping(wait_ms=1000):
    """Round-trip ping the PR-offload MCU over the bridge."""
    return pr_bridge.send_command({"cmd": "ping"}, wait_ms=wait_ms)


def pr_status(wait_ms=1000):
    """Request the PR-offload runtime status (remote cadence, seq, timestamps)."""
    return pr_bridge.send_command({"cmd": "status"}, wait_ms=wait_ms)


def pr_request_snapshot(wait_ms=1000):
    """Request a synchronous snapshot directly from the PR-offload MCU."""
    return pr_bridge.send_command({"cmd": "snapshot"}, wait_ms=wait_ms)


def pr_version(wait_ms=1000):
    """Fetch PR-offload firmware/protocol version info."""
    return pr_bridge.send_command({"cmd": "version"}, wait_ms=wait_ms)


def pr_poll_control(action, wait_ms=1000):
    """Pause/resume the PR-offload poller (action=start|resume|pause|stop)."""
    action_norm = str(action or "").lower()
    if action_norm not in ("start", "resume", "pause", "stop"):
        raise ValueError("action must be start/resume/pause/stop")
    return pr_bridge.send_command({"cmd": "poll", "action": action_norm}, wait_ms=wait_ms)


def pr_offload_reboot(wait_ms=1000):
    """Command the PR-offload MCU to reboot itself."""
    return pr_bridge.send_command({"cmd": "reboot"}, wait_ms=wait_ms)


def pr_offload_sleep(
    wait_ms=2000,
    delay_s=2,
    *,
    retries=1,
):
    """Command the PR-offload MCU to enter deep sleep after ``delay_s`` seconds."""
    try:
        delay_val = max(0, int(delay_s))
    except Exception:
        delay_val = 10
    payload = {"cmd": "sleepNow", "delay_s": delay_val}
    last_error = None
    attempts = max(1, int(retries) + 1)
    resp = None
    for attempt in range(attempts):
        try:
            resp = pr_bridge.send_command(payload, wait_ms=wait_ms)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            print("[t] pr_offload_sleep: attempt {} failed".format(attempt + 1), exc)
            if attempt + 1 < attempts:
                try:
                    sleep_ms(200)
                except Exception:
                    pass
    if last_error is not None:
        raise last_error

    return resp


def pr_offload_wifi_connect(wait_ms=5000):
    """Ask the PR-offload MCU to run the frozen wifiConnect module."""
    return pr_bridge.send_command({"cmd": "wifi_connect"}, wait_ms=wait_ms)


def _ensure_pr_wake_pin(default_level=1):
    global _PR_WAKE_PIN
    if PR_OFFLOAD_WAKE_PIN is None or PR_OFFLOAD_WAKE_PIN < 0:
        raise RuntimeError("PR_OFFLOAD_WAKE_PIN not configured")
    pin = _PR_WAKE_PIN
    if pin is None:
        pin = make_output(PR_OFFLOAD_WAKE_PIN, value=int(bool(default_level)))
        _PR_WAKE_PIN = pin
    elif default_level is not None:
        pin.value(int(bool(default_level)))
    return pin


def pr_offload_hold_awake(enabled=True):
    """Drive the dedicated wake GPIO HIGH (True) or LOW (False)."""
    level = 1 if enabled else 0
    pin = _ensure_pr_wake_pin(level)
    pin.value(level)
    return True


def pr_offload_allow_sleep():
    """Convenience helper to drop the wake line LOW so the offload can sleep."""
    return pr_offload_hold_awake(False)


def pr_offload_wake(pulse_ms=50):
    """Hold the wake GPIO HIGH to start or keep the offload MCU awake."""
    try:
        duration = max(5, int(pulse_ms))
    except Exception:
        duration = 50
    pr_offload_hold_awake(True)
    sleep_ms(duration)
    return True


def _get_cellular_modem():
    try:
        from CellularLte import modem as _lte_modem  # type: ignore
    except Exception as exc:
        print("[t] modem helper import failed:", exc)
        return None
    return _lte_modem


def modem_power_off():
    """Power down the onboard SIM7600 module via its GPIO sequence."""
    modem = _get_cellular_modem()
    if modem is None:
        return False
    try:
        modem.modem_off()
        return True
    except Exception as exc:
        print("[t] modem_power_off error:", exc)
        return False


def modem_power_on(*, wait_for_registration=True, timeout_ms=30_000):
    """Power up the onboard SIM7600 module and optionally wait for network attach."""
    modem = _get_cellular_modem()
    if modem is None:
        return False
    try:
        modem.modem_on()
        ensure_reader = getattr(modem, "ensure_reader", None)
        if callable(ensure_reader):
            try:
                ensure_reader()
            except Exception as exc:
                print("[t] modem_power_on reader warn:", exc)
        for cmd in ("AT+CFUN=1", "AT+CNMP=2", "AT+CMNB=3"):
            try:
                modem.send_at(cmd)
            except Exception:
                pass
        if wait_for_registration:
            reg = modem_wait_for_registration(timeout_ms=timeout_ms, verbose=True)
            if reg:
                print("[t] modem registered:", reg.get("state"))
        return True
    except Exception as exc:
        print("[t] modem_power_on error:", exc)
        return False


def _auto_disable_modem_on_boot():
    try:
        success = modem_power_off()
    except Exception as exc:
        try:
            print("[t] startup: modem auto-off error:", exc)
        except Exception:
            pass
        return False
    if success:
        print("[t] startup: modem forced OFF")
    else:
        print("[t] startup: modem auto-off skipped (unavailable)")
    return success



def _parse_creg_response(lines):
    if not lines:
        return None
    state_map = {
        "0": "not registered",
        "1": "home",
        "2": "searching",
        "3": "denied",
        "5": "roaming",
    }
    for line in lines:
        if not isinstance(line, str):
            continue
        payload = line.strip()
        if not payload.startswith("+CREG:"):
            continue
        try:
            _, rest = payload.split(":", 1)
            parts = [segment.strip() for segment in rest.split(",")]
        except Exception:
            continue
        code = parts[1] if len(parts) > 1 else None
        return {"raw": payload, "code": code, "state": state_map.get(code, "code {}".format(code))}
    return None


def _cpin_ready(lines):
    if not lines:
        return False
    for line in lines:
        if isinstance(line, str) and "+CPIN:" in line and "READY" in line.upper():
            return True
    return False


def modem_wait_for_registration(*, timeout_ms=30_000, poll_ms=1_500, verbose=False):
    modem = _get_cellular_modem()
    if modem is None:
        return None
    send_at = getattr(modem, "send_at", None)
    if not callable(send_at):
        return None
    poll_ms = max(200, int(poll_ms))
    timeout_ms = max(poll_ms, int(timeout_ms))
    deadline = ticks_add(ticks_ms(), timeout_ms)
    last_state = None
    while ticks_diff(deadline, ticks_ms()) > 0:
        try:
            if not _cpin_ready(send_at("AT+CPIN?")):
                if verbose:
                    print("[t] modem_wait_for_registration: SIM not ready")
                sleep_ms(poll_ms)
                continue
        except Exception as exc:
            if verbose:
                print("[t] modem_wait_for_registration CPIN error:", exc)
        try:
            reg = _parse_creg_response(send_at("AT+CREG?"))
        except Exception as exc:
            if verbose:
                print("[t] modem_wait_for_registration CREG error:", exc)
            reg = None
        if reg is not None:
            code = reg.get("code")
            if code in {"1", "5"}:
                return reg
            if verbose and reg != last_state:
                print("[t] modem registration state:", reg.get("state"))
            last_state = reg
        sleep_ms(poll_ms)
    if verbose and last_state is None:
        print("[t] modem_wait_for_registration: timeout")
    return last_state


def modem_collect_snapshot(power_down=False, *, wifi_limit=3, ensure_power=True):
    """Return the SIM7600 telemetry snapshot via the CellularLte modem helper."""

    modem = _get_cellular_modem()
    if modem is None:
        return None
    collect = getattr(modem, "collect_snapshot", None)
    if not callable(collect):
        print("[t] modem_collect_snapshot: collect_snapshot missing")
        return None
    try:
        snapshot = collect(
            power_down=power_down,
            wifi_limit=wifi_limit,
            ensure_power=ensure_power,
        )
    except TypeError:
        try:
            snapshot = collect()
        except Exception as exc:
            print("[t] modem_collect_snapshot error:", exc)
            return None
    except Exception as exc:
        print("[t] modem_collect_snapshot error:", exc)
        return None
    return snapshot


def print_modem_snapshot(power_down=False, *, wifi_limit=3, ensure_power=True):
    """Convenience wrapper that prints the modem snapshot via CellularLte.modem."""

    modem = _get_cellular_modem()
    if modem is None:
        return None
    printer = getattr(modem, "print_snapshot", None)
    if not callable(printer):
        print("[t] print_modem_snapshot: print_snapshot missing")
        return None
    try:
        snapshot = printer(
            wifi_limit=wifi_limit,
            ensure_power=ensure_power,
            power_down=power_down,
        )
    except TypeError:
        try:
            snapshot = printer()
        except Exception as exc:
            print("[t] print_modem_snapshot error:", exc)
            return None
    except Exception as exc:
        print("[t] print_modem_snapshot error:", exc)
        return None
    return snapshot


def _coerce_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _compile_wifi_entries(snapshot, limit=2):
    if snapshot is None:
        return []
    try:
        limit = max(1, int(limit))
    except Exception:
        limit = 2
    entries = []
    wifi_list = snapshot.get("wifi_list") if isinstance(snapshot, dict) else None
    candidates = wifi_list if isinstance(wifi_list, list) else []
    if not candidates:
        single = snapshot.get("wifi") if isinstance(snapshot, dict) else None
        if isinstance(single, dict):
            candidates = [single]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        entries.append({
            "ssid": item.get("ssid"),
            "bssid": item.get("bssid"),
            "rssi": item.get("rssi"),
        })
    entries.sort(key=lambda e: e.get("rssi") if isinstance(e.get("rssi"), (int, float)) else -200, reverse=True)
    return entries[:limit]


def _parse_cell_info_meta(cell_info, cell_meta=None):
    if isinstance(cell_meta, dict) and cell_meta:
        meta = dict(cell_meta)
        meta.setdefault("raw", cell_meta.get("raw", ""))
    else:
        meta = {"raw": cell_info or ""}
    meta.setdefault("neighbor_ids", [])
    if cell_meta:
        return meta
    if not cell_info:
        return meta
    parts = [segment.strip() for segment in cell_info.split(",") if segment.strip()]
    if not parts:
        return meta
    fields = {
        "rat": parts[0] if len(parts) > 0 else None,
        "status": parts[1] if len(parts) > 1 else None,
        "mcc_mnc": parts[2] if len(parts) > 2 else None,
        "tracking_area": parts[3] if len(parts) > 3 else None,
        "cell_id": parts[4] if len(parts) > 4 else None,
        "pci": parts[5] if len(parts) > 5 else None,
        "band": parts[6] if len(parts) > 6 else None,
        "earfcn": parts[7] if len(parts) > 7 else None,
    }
    meta.update(fields)
    numeric_ids = []
    for token in parts:
        token_clean = token.replace(" ", "")
        if token_clean.startswith("0x"):
            continue
        if token_clean.isdigit() and len(token_clean) >= 6:
            numeric_ids.append(token_clean)
    if numeric_ids:
        meta["primary_id"] = numeric_ids[0]
        meta["neighbor_ids"] = numeric_ids[1:2]
    elif fields.get("cell_id"):
        meta["primary_id"] = fields.get("cell_id")
    return meta


def _build_cell_section(snapshot):
    data = snapshot or {}
    operator = data.get("operator") or {}
    registration = data.get("registration") or {}
    signal = data.get("signal") or {}
    cell_info = data.get("cell_info")
    cell_lines = data.get("cell_info_lines")
    info = _parse_cell_info_meta(cell_info, data.get("cell_info_meta"))
    neighbor_details = []
    raw_neighbors = data.get("cell_neighbors")
    if isinstance(raw_neighbors, list):
        for entry in raw_neighbors:
            if not isinstance(entry, dict):
                continue
            detail = {
                "cell_id": entry.get("cell_id"),
                "tac": entry.get("tac"),
                "pci": entry.get("pci"),
                "plmn": entry.get("plmn"),
                "mcc": entry.get("mcc"),
                "mnc": entry.get("mnc"),
                "rat": entry.get("rat"),
                "signal_dbm": entry.get("signal_dbm"),
                "signal_aux": entry.get("signal_aux"),
                "raw": entry.get("raw"),
            }
            label = detail.get("cell_id") or detail.get("tac") or detail.get("raw")
            if label:
                detail["label"] = label
            neighbor_details.append(detail)
    if neighbor_details:
        info.setdefault("neighbor_ids", [])
        if not info["neighbor_ids"]:
            derived_ids = [entry.get("cell_id") for entry in neighbor_details if entry.get("cell_id")]
            if derived_ids:
                info["neighbor_ids"] = derived_ids[:2]
    section = {
        "operator": operator.get("operator") or operator.get("name"),
        "mode": operator.get("mode"),
        "act": operator.get("act"),
        "registration": registration.get("state"),
        "signal": {
            "csq": signal.get("csq"),
            "rssi_dbm": signal.get("rssi_dbm"),
        },
        "info": info,
        "raw_lines": cell_lines,
        "primary_id": info.get("primary_id"),
        "neighbor_ids": info.get("neighbor_ids", []),
        "neighbor_details": neighbor_details[:2],
    }
    return section


def _build_gps_section(gnss):
    source = gnss or {}
    return {
        "fix": bool(source.get("fix")),
        "sats": _coerce_float(source.get("sats")),
        "lat": _coerce_float(source.get("lat")),
        "lon": _coerce_float(source.get("lon")),
        "alt": _coerce_float(source.get("alt")),
        "speed": _coerce_float(source.get("speed")),
        "raw": source,
    }


def _build_sys_battery_section():
    snap = battery_status_snapshot()
    if not isinstance(snap, dict):
        return None
    return {
        "vbus_v": snap.get("vbus_v"),
        "vbat_v": snap.get("vbat_v"),
        "ichg_ma": snap.get("ichg_ma"),
        "idis_ma": snap.get("idis_ma"),
        "sys_i_ma": snap.get("sys_i_ma"),
        "flags": snap.get("flags"),
    }


def _build_pr_battery_section(state):
    if state is None:
        return None
    try:
        voltage = state.get_pr("battery_voltage", (None, ""))[0]
    except Exception:
        voltage = None
    try:
        current = state.get_pr("battery_current", (None, ""))[0]
    except Exception:
        current = None
    try:
        power = state.get_pr("motor_input_power", (None, ""))[0]
    except Exception:
        power = None
    voltage_f = _coerce_float(voltage)
    current_f = _coerce_float(current)
    power_f = _coerce_float(power)
    if voltage_f is None and current_f is None and power_f is None:
        return None
    return {
        "voltage_v": voltage_f,
        "current_a": current_f,
        "power_w": power_f,
    }


def collect_alarm_snapshot(*, power_down_modem=False, wifi_limit=2, include_sys_battery=True, include_pr_battery=True):
    """Collect a modem snapshot and feed alarm telemetry sections.

    Returns a dict with ``cell``, ``gps``, ``wifi`` (top-N entries), and ``battery``
    sections ready for dashboard or SMS usage. The main AppState is updated when
    available so the alarm dashboard reflects the latest data.
    """

    snapshot = modem_collect_snapshot(power_down=power_down_modem, wifi_limit=wifi_limit)
    if snapshot is None:
        return None
    wifi_entries = _compile_wifi_entries(snapshot, limit=wifi_limit)
    cell_section = _build_cell_section(snapshot)
    gps_section = _build_gps_section(snapshot.get("gnss") or {})
    sys_batt = _build_sys_battery_section() if include_sys_battery else None
    pr_batt = _build_pr_battery_section(_state) if include_pr_battery else None
    result = {
        "timestamp": snapshot.get("timestamp"),
        "cell": cell_section,
        "gps": gps_section,
        "wifi": wifi_entries,
        "battery": {
            "sys": sys_batt,
            "pr": pr_batt,
        },
        "raw_snapshot": snapshot,
    }
    state = _state
    if state is not None:
        now = ticks_ms()
        state.alarm_active = True
        state.alarm_last_update_ms = now
        signal = cell_section.get("signal") or {}
        state.alarm_signal_csq = signal.get("csq")
        state.alarm_signal_rssi_dbm = signal.get("rssi_dbm")
        state.alarm_operator = cell_section.get("operator") or ""
        info = cell_section.get("info") or {}
        state.alarm_cell_info = info.get("raw") or ""
        state.alarm_registration = cell_section.get("registration") or ""
        state.alarm_cell_primary = info.get("primary_id") or ""
        state.alarm_cell_neighbors = info.get("neighbor_ids") or []
        state.alarm_cell_neighbor_details = cell_section.get("neighbor_details") or []
        state.alarm_wifi_list = wifi_entries
        state.alarm_gnss_fix = gps_section.get("fix", False)
        state.alarm_gnss_lat = gps_section.get("lat")
        state.alarm_gnss_lon = gps_section.get("lon")
        state.alarm_gnss_alt = gps_section.get("alt")
        state.alarm_gnss_sats = gps_section.get("sats") or 0
        state.alarm_gnss_speed = gps_section.get("speed")
        state.alarm_sys_batt = sys_batt
        state.alarm_pr_batt = pr_batt
        state.alarm_snapshot = result
    return result


def _prime_pr_wake_line_on_import():
    if PR_OFFLOAD_WAKE_PIN is None or PR_OFFLOAD_WAKE_PIN < 0:
        return False
    try:
        pr_offload_hold_awake(True)
        print("[t] startup: PR-offload wake line HIGH on GPIO{}".format(PR_OFFLOAD_WAKE_PIN))
        return True
    except Exception as exc:
        try:
            print("[t] startup: wake line init skipped", exc)
        except Exception:
            pass
        return False


_PR_WAKE_LINE_PRIMED = _prime_pr_wake_line_on_import()


_PMU_INSTANCE = None


def _get_pmu_device(refresh=False):
    global _PMU_INSTANCE
    if not refresh and _PMU_INSTANCE is not None:
        return _PMU_INSTANCE
    try:
        from drivers.axp192 import AXP192  # type: ignore
    except Exception as exc:
        print("[t] battery helper missing drivers.axp192:", exc)
        return None
    try:
        i2c = make_i2c()
    except Exception as exc:
        print("[t] battery helper I2C error:", exc)
        return None
    try:
        pmu = AXP192(i2c)
    except Exception as exc:
        print("[t] battery helper AXP192 init error:", exc)
        return None
    _PMU_INSTANCE = pmu
    return pmu


def _format_pmu_flags(power_status, charge_status):
    merged = {}
    if isinstance(power_status, dict):
        merged.update(power_status)
    if isinstance(charge_status, dict):
        merged.update(charge_status)
    flags = []
    if merged.get("acin_present"):
        flags.append("AC")
    if merged.get("vbus_present"):
        flags.append("VBUS")
    if merged.get("battery_present"):
        flags.append("BAT")
    if merged.get("charging"):
        flags.append("CHG")
    if merged.get("charge_complete"):
        flags.append("FULL")
    if merged.get("battery_overtemp"):
        flags.append("HOT")
    if not flags:
        flags.append("IDLE")
    return ",".join(flags)


def battery_status_snapshot(refresh_pmu=False):
    """Return a one-shot AXP192 measurement similar to ``testBatt`` output."""

    pmu = _get_pmu_device(refresh=refresh_pmu)
    if pmu is None:
        return None
    try:
        vbus_v = pmu.read_vbus_voltage() / 1000.0
        vbus_i = pmu.read_vbus_current()
        vbat_v = pmu.read_vbat_voltage() / 1000.0
        ichg = pmu.read_battery_charge_current()
        idis = pmu.read_battery_discharge_current()
        power_status = pmu.get_power_status()
        charge_status = pmu.get_charge_status()
    except Exception as exc:
        print("[t] battery_status_snapshot read error:", exc)
        return None
    flags = _format_pmu_flags(power_status, charge_status)
    sys_i = None
    try:
        if power_status and not power_status.get("battery_present"):
            sys_i = vbus_i
    except Exception:
        sys_i = None
    return {
        "vbus_v": vbus_v,
        "vbus_i": vbus_i,
        "vbat_v": vbat_v,
        "ichg_ma": ichg,
        "idis_ma": idis,
        "sys_i_ma": sys_i,
        "flags": flags,
        "power_status": power_status,
        "charge_status": charge_status,
    }


def print_battery_status(refresh_pmu=False):
    snap = battery_status_snapshot(refresh_pmu=refresh_pmu)
    if not snap:
        print("[t] battery status unavailable")
        return None
    sys_txt = "SYS={:.1f} mA | ".format(snap["sys_i_ma"]) if snap["sys_i_ma"] is not None else ""
    print(
        "VBUS={:.2f} V {:.1f} mA | {}VBAT={:.2f} V chg={:.1f} mA dis={:.1f} mA | {}".format(
            snap["vbus_v"],
            snap["vbus_i"],
            sys_txt,
            snap["vbat_v"],
            snap["ichg_ma"],
            snap["idis_ma"],
            snap["flags"],
        )
    )
    return snap


def release_pr_uart_lines():
    """Put the PR UART pins into a neutral state before powering down."""

    try:
        import machine  # type: ignore
    except Exception:
        return False

    try:
        uart = machine.UART(PR_UART_ID)
        uart.deinit()
    except Exception:
        pass

    pull_up = getattr(machine.Pin, "PULL_UP", None)
    success = True
    for pin_num in (PR_UART_TX, PR_UART_RX):
        try:
            if pull_up is not None:
                make_input(pin_num, pull_up)
            else:
                make_input(pin_num)
        except Exception:
            success = False
    return success


def get_pr_snapshot(raw=False):
    """Return cached Phaserunner telemetry (AppState or raw bridge frame)."""
    if raw:
        return pr_bridge_latest_payload()
    if _state is None:
        return {}
    return _state.snapshot_pr()


def get_ui_intervals():
    """Return (ui_frame_ms, integrator_ms)."""
    return int(_UI_FRAME_MS), int(_INTEGRATOR_MS)


def set_ui_frame_interval(ms=None):
    """Set or query UI redraw cadence in milliseconds (min 20)."""
    global _UI_FRAME_MS
    if ms is None:
        return int(_UI_FRAME_MS)
    try:
        value = int(ms)
    except Exception:
        raise ValueError("invalid UI interval")
    if value < 20:
        value = 20
    _UI_FRAME_MS = value
    return int(_UI_FRAME_MS)


def set_integrator_interval(ms=None):
    """Set or query integrator step interval in milliseconds (min 50)."""
    global _INTEGRATOR_MS
    if ms is None:
        return int(_INTEGRATOR_MS)
    try:
        value = int(ms)
    except Exception:
        raise ValueError("invalid integrator interval")
    if value < 50:
        value = 50
    _INTEGRATOR_MS = value
    return int(_INTEGRATOR_MS)


def configure_gc_task(*, enabled=None, interval_ms=None, verbose=None):
    """Configure the background garbage collection coroutine."""
    global _GC_TASK_ENABLED, _GC_INTERVAL_MS, _GC_VERBOSE
    if enabled is not None:
        _GC_TASK_ENABLED = bool(enabled)
    if interval_ms is not None:
        try:
            value = int(interval_ms)
        except Exception:
            raise ValueError("invalid GC interval")
        if value < 1000:
            value = 1000
        _GC_INTERVAL_MS = value
    if verbose is not None:
        _GC_VERBOSE = bool(verbose)
    return {
        "enabled": _GC_TASK_ENABLED,
        "interval_ms": _GC_INTERVAL_MS,
        "verbose": _GC_VERBOSE,
    }


def set_signals_interval(ms=None):
    """Set or query the Signals dashboard redraw cadence (ms)."""
    dash = _dashboard_signals
    if dash is None:
        raise RuntimeError("signals dashboard not available")
    if ms is None:
        return dash.get_tick_interval()
    if not dash.set_tick_interval(ms):
        raise ValueError("invalid signals interval")
    return dash.get_tick_interval()


def debug_signals_timing(enable=True, threshold_ms=None):
    """Toggle timing diagnostics for the Signals dashboard."""
    dash = _dashboard_signals
    if dash is None:
        raise RuntimeError("signals dashboard not available")
    setter = getattr(dash, "set_debug_timing", None)
    if not callable(setter):
        raise RuntimeError("signals dashboard debug not supported")
    result = setter(enable, threshold_ms)
    if result:
        if threshold_ms is None:
            threshold_ms = dash._debug_threshold_ms  # type: ignore[attr-defined]
        print("[t] signals timing debug ON (threshold {} ms)".format(threshold_ms))
    else:
        print("[t] signals timing debug OFF")
    return result


def set_button_debug(enable=True):
    """Enable verbose timing logs for Page/Up/Down button events."""
    try:
        enable_flag = bool(enable)
    except Exception:
        enable_flag = True
    _buttons_mod.DEBUG = enable_flag
    state = "ON" if enable_flag else "OFF"
    print("[t] button debug {}".format(state))
    return enable_flag


def set_updown_thresholds(*, up_max=None, down_max=None):
    """Adjust ADC thresholds for the Up/Down buttons at runtime."""
    btn = _updown_buttons
    if btn is None:
        raise RuntimeError("up/down buttons not initialized")
    updated = False
    if up_max is not None:
        try:
            value = int(up_max)
            if value < 0:
                value = 0
            btn.UP_MAX = value
            updated = True
        except Exception:
            raise ValueError("invalid up_max")
    if down_max is not None:
        try:
            value = int(down_max)
            if value < btn.UP_MAX + 10:
                value = btn.UP_MAX + 10
            btn.DOWN_MAX = value
            updated = True
        except Exception:
            raise ValueError("invalid down_max")
    if not updated:
        return {"UP_MAX": btn.UP_MAX, "DOWN_MAX": btn.DOWN_MAX}
    print("[t] up/down thresholds -> UP:{} DOWN:{}".format(btn.UP_MAX, btn.DOWN_MAX))
    return {"UP_MAX": btn.UP_MAX, "DOWN_MAX": btn.DOWN_MAX}


def sample_updown_adc(samples=16, delay_ms=20):
    """Read raw ADC samples for the Up/Down rocker to aid calibration."""
    try:
        adc = make_adc(UPDOWN_ADC_PIN)
    except Exception as exc:
        raise RuntimeError("unable to access up/down ADC: {}".format(exc))
    reader = getattr(adc, "read", None) or getattr(adc, "read_u16", None)
    if not callable(reader):
        raise RuntimeError("adc read method unavailable")
    samples = max(1, int(samples))
    delay_ms = max(0, int(delay_ms))
    values = []
    for idx in range(samples):
        try:
            raw = reader()
        except Exception as exc:
            raise RuntimeError("adc read failed: {}".format(exc))
        values.append(int(raw))
        if delay_ms and idx + 1 < samples:
            sleep_ms(delay_ms)
    return values


def set_trip_interval(ms=None):
    """Set or query the Trip dashboard redraw cadence (ms)."""
    dash = _dashboard_trip
    if dash is None:
        raise RuntimeError("trip dashboard not available")
    if ms is None:
        return dash.get_tick_interval()
    if not dash.set_tick_interval(ms):
        raise ValueError("invalid trip interval")
    return dash.get_tick_interval()


def set_trip_counter_interval(ms=None):
    """Set or query the pulse-to-speed sampling interval (ms)."""
    global _TRIP_COUNTER_INTERVAL_MS
    if ms is None:
        return int(_TRIP_COUNTER_INTERVAL_MS)
    try:
        value = int(ms)
    except Exception:
        raise ValueError("invalid interval")
    if value < 100:
        value = 100
    _TRIP_COUNTER_INTERVAL_MS = value
    print("[t] trip counter interval -> {} ms".format(value))
    return value


def set_battery_interval(ms=None):
    """Set or query the battery status dashboard redraw cadence (ms)."""
    dash = _dashboard_batt_status
    if dash is None:
        raise RuntimeError("battery status dashboard not available")
    if ms is None:
        return dash.get_tick_interval()
    if not dash.set_tick_interval(ms):
        raise ValueError("invalid battery interval")
    return dash.get_tick_interval()


def list_battery_packs():
    """Return available battery pack identifiers."""
    return bats.available_packs()


def show_battery_pack(name=None):
    """Return the metadata for the given battery pack."""
    return bats.pack_info(name)


def save_battery_pack(name, **params):
    """Persist or update a battery pack definition."""
    pack = bats.save_pack(name, **params)
    if _state is not None:
        _state.set_battery_pack(pack)
    for dash in (_dashboard_batt_select, _dashboard_batt_status):
        if dash is not None and hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()
    return pack


def select_battery_pack(name):
    """Select a battery pack to be used by the runtime."""
    pack = bats.set_current_pack(name)
    if _state is not None:
        _state.set_battery_pack(pack)
    for dash in (_dashboard_batt_select, _dashboard_batt_status):
        if dash is not None and hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()
    return pack


def reload_battery_pack():
    """Reload the active battery pack from configuration."""
    pack = bats.load_current_pack()
    if _state is not None:
        _state.set_battery_pack(pack)
    for dash in (_dashboard_batt_select, _dashboard_batt_status):
        if dash is not None and hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()
    return pack


def battery_pack_details():
    """Return a dict with all known battery pack definitions."""
    return bats.pack_details()


def get_page_button_timings():
    """Return the current Page button timing dictionary."""
    btn = _page_button
    if btn is None:
        raise RuntimeError("page button not initialized")
    return dict(btn.t)


def set_page_button_timings(**timings):
    """Set or query Page button timing parameters (keys match defaults)."""
    btn = _page_button
    if btn is None:
        raise RuntimeError("page button not initialized")
    if not timings:
        return get_page_button_timings()
    updated = False
    for key, value in timings.items():
        if key is None:
            continue
        name = str(key).upper()
        if name not in btn.t:
            continue
        try:
            btn.t[name] = int(value)
            updated = True
        except Exception:
            raise ValueError("invalid value for {}".format(name))
    if not updated:
        return False
    return get_page_button_timings()


def debug_on():
    """Activa heartbeat en consola."""
    global _HB_TASK
    if _HB_TASK is None and _state is not None:
        _HB_TASK = _track_task(asyncio.create_task(heartbeat_task(_state)))
        print("[t] debug ON")


def debug_off():
    """Desactiva heartbeat en consola."""
    global _HB_TASK
    if _HB_TASK is not None:
        _HB_TASK.cancel()
        try:
            _TASKS.remove(_HB_TASK)
        except Exception:
            pass
        _HB_TASK = None
        print("[t] debug OFF")


def _resolve_control_loop_debug_state():
    motor = _motor
    if motor is None and _state is not None:
        motor = getattr(_state, "motor_control", None)
    cfg = getattr(motor, "cfg", {}) if motor is not None else {}
    current_enabled = bool(cfg.get("monitor_control_enabled", False))
    try:
        current_period = int(cfg.get("monitor_control_period_ms", 1000))
    except Exception:
        current_period = 1000
    desired_enabled = current_enabled if _CONTROL_LOOP_DEBUG_OVERRIDE is None else bool(_CONTROL_LOOP_DEBUG_OVERRIDE)
    if _CONTROL_LOOP_DEBUG_PERIOD_MS is None:
        desired_period = current_period
    else:
        try:
            desired_period = int(_CONTROL_LOOP_DEBUG_PERIOD_MS)
        except Exception:
            desired_period = current_period
    if desired_period < 200:
        desired_period = 200
    return motor, desired_enabled, desired_period


def _apply_control_loop_debug_pref(*, quiet=False):
    motor, desired_enabled, desired_period = _resolve_control_loop_debug_state()
    if motor is None:
        return False
    setter = getattr(motor, "set_monitor_debug", None)
    if not callable(setter):
        if not quiet:
            print("[t] control loop debug unsupported by motor controller")
        return False
    try:
        setter(desired_enabled, period_ms=desired_period)
    except Exception as exc:
        if not quiet:
            print("[t] control loop debug apply error:", exc)
        return False
    if not quiet:
        state_label = "ON" if desired_enabled else "OFF"
        if desired_enabled:
            print("[t] control loop debug {} ({} ms)".format(state_label, desired_period))
        else:
            print("[t] control loop debug {}".format(state_label))
    return True


def enable_control_loop_debug(enable=None, period_ms=None):
    """Enable/disable the MotorControl loop diagnostics (1 Hz printouts)."""
    global _CONTROL_LOOP_DEBUG_OVERRIDE, _CONTROL_LOOP_DEBUG_PERIOD_MS
    if enable is not None:
        _CONTROL_LOOP_DEBUG_OVERRIDE = bool(enable)
    if period_ms is not None:
        try:
            value = int(period_ms)
        except Exception:
            raise ValueError("invalid monitor period")
        if value < 200:
            value = 200
        _CONTROL_LOOP_DEBUG_PERIOD_MS = value
    applied = _apply_control_loop_debug_pref()
    if not applied and _CONTROL_LOOP_DEBUG_OVERRIDE is not None:
        print("[t] control loop debug request queued (motor not ready)")
    if enable is None and period_ms is None:
        _, desired_enabled, desired_period = _resolve_control_loop_debug_state()
        return {"enabled": desired_enabled, "period_ms": desired_period}
    return bool(_CONTROL_LOOP_DEBUG_OVERRIDE if _CONTROL_LOOP_DEBUG_OVERRIDE is not None else False)


def set_control_monitor_compact(enable=None, delta_pct=None):
    """Show only anomalous monitor rows with a simplified ADC/target/speed/DAC line."""
    motor = _get_motor_controller()
    if motor is None:
        raise RuntimeError("motor controller not ready")
    setter = getattr(motor, "set_monitor_compact_mode", None)
    if not callable(setter):
        raise RuntimeError("monitor compact mode unsupported")
    result = setter(anomalies_only=enable, delta_pct=delta_pct)
    if enable is not None:
        state_label = "ON" if result.get("anomalies_only") else "OFF"
        threshold = result.get("delta_pct", 0.0)
        print("[t] control monitor compact {} (threshold {:.1f}%)".format(state_label, threshold))
    if enable is None and delta_pct is None:
        return result
    return result.get("anomalies_only")


def set_loop_timing_monitor(enable=None):
    """Toggle whether loop timing metrics appear in the control monitor output."""
    global _LOOP_TIMING_MONITOR_OVERRIDE
    if enable is not None:
        _LOOP_TIMING_MONITOR_OVERRIDE = bool(enable)
    applied = _apply_loop_timing_monitor_pref()
    if not applied and _LOOP_TIMING_MONITOR_OVERRIDE is not None:
        print("[t] loop timing monitor request queued (motor not ready)")
    if enable is None:
        _, desired_enabled = _resolve_loop_timing_monitor_state()
        return bool(desired_enabled)
    return bool(_LOOP_TIMING_MONITOR_OVERRIDE if _LOOP_TIMING_MONITOR_OVERRIDE is not None else False)


def set_pid_timing_debug(enable=None, period_ms=None):
    """Enable/disable the detailed PID math timing diagnostic output."""
    global _PID_TIMING_DEBUG_OVERRIDE, _PID_TIMING_DEBUG_PERIOD_MS
    if enable is not None:
        _PID_TIMING_DEBUG_OVERRIDE = bool(enable)
    if period_ms is not None:
        try:
            value = int(period_ms)
        except Exception:
            raise ValueError("invalid pid timing debug period")
        if value < 200:
            value = 200
        _PID_TIMING_DEBUG_PERIOD_MS = value
    applied = _apply_pid_timing_debug_pref()
    if not applied and _PID_TIMING_DEBUG_OVERRIDE is not None:
        print("[t] pid timing debug request queued (motor not ready)")
    if enable is None and period_ms is None:
        _, desired_enabled, desired_period = _resolve_pid_timing_debug_state()
        return {"enabled": desired_enabled, "period_ms": desired_period}
    return bool(_PID_TIMING_DEBUG_OVERRIDE if _PID_TIMING_DEBUG_OVERRIDE is not None else False)


def _normalize_pid_mode(mode):
    try:
        label = str(mode or "").strip().lower()
    except Exception:
        label = ""
    if label in {"spd", "speed_mode"}:
        return "speed"
    if label in {"pow", "power_mode"}:
        return "power"
    if label in {"tor", "torque_mode", "nm"}:
        return "torque"
    normalized = label or "power"
    if normalized not in {"power", "speed", "torque"}:
        raise ValueError("mode must be power, speed, or torque for PID tuning")
    return normalized


def _get_motor_controller():
    motor = _motor
    if motor is None and _state is not None:
        motor = getattr(_state, "motor_control", None)
    return motor


def _resolve_loop_timing_monitor_state():
    motor = _get_motor_controller()
    cfg = getattr(motor, "cfg", {}) if motor is not None else {}
    current_enabled = bool(cfg.get("loop_timing_monitor_enabled", False))
    desired_enabled = current_enabled if _LOOP_TIMING_MONITOR_OVERRIDE is None else bool(_LOOP_TIMING_MONITOR_OVERRIDE)
    return motor, desired_enabled


def _apply_loop_timing_monitor_pref(*, quiet=False):
    motor, desired_enabled = _resolve_loop_timing_monitor_state()
    if motor is None:
        return False
    setter = getattr(motor, "set_loop_timing_monitor", None)
    if not callable(setter):
        if not quiet:
            print("[t] loop timing monitor unsupported by motor controller")
        return False
    try:
        setter(desired_enabled)
    except Exception as exc:
        if not quiet:
            print("[t] loop timing monitor apply error:", exc)
        return False
    if not quiet:
        state_label = "ON" if desired_enabled else "OFF"
        print("[t] loop timing monitor {}".format(state_label))
    return True


def _resolve_pid_timing_debug_state():
    motor = _get_motor_controller()
    cfg = getattr(motor, "cfg", {}) if motor is not None else {}
    current_enabled = bool(cfg.get("pid_timing_debug_enabled", False))
    try:
        current_period = int(cfg.get("pid_timing_debug_period_ms", 1000))
    except Exception:
        current_period = 1000
    desired_enabled = current_enabled if _PID_TIMING_DEBUG_OVERRIDE is None else bool(_PID_TIMING_DEBUG_OVERRIDE)
    if _PID_TIMING_DEBUG_PERIOD_MS is None:
        desired_period = current_period
    else:
        try:
            desired_period = max(200, int(_PID_TIMING_DEBUG_PERIOD_MS))
        except Exception:
            desired_period = current_period
    return motor, desired_enabled, desired_period


def _apply_pid_timing_debug_pref(*, quiet=False):
    motor, desired_enabled, desired_period = _resolve_pid_timing_debug_state()
    if motor is None:
        return False
    setter = getattr(motor, "set_pid_timing_debug", None)
    if not callable(setter):
        if not quiet:
            print("[t] pid timing debug unsupported by motor controller")
        return False
    try:
        setter(desired_enabled, period_ms=desired_period)
    except Exception as exc:
        if not quiet:
            print("[t] pid timing debug apply error:", exc)
        return False
    if not quiet:
        state_label = "ON" if desired_enabled else "OFF"
        if desired_enabled:
            print("[t] pid timing debug {} ({} ms)".format(state_label, desired_period))
        else:
            print("[t] pid timing debug {}".format(state_label))
    return True


def _get_motor_cfg_ref():
    motor = _get_motor_controller()
    cfg = getattr(motor, "cfg", None)
    if isinstance(cfg, dict):
        return cfg
    return load_motor_config()


def get_pid_params(mode=None, *, include_guidance=True):
    """Return PID parameters for a given mode (or all modes if None)."""
    cfg = _get_motor_cfg_ref()
    if mode is None:
        modes = ("power", "speed", "torque")
        return {label: get_pid_params(label, include_guidance=include_guidance) for label in modes}
    label = _normalize_pid_mode(mode)
    data = {}
    for canonical in ("kp", "ki", "kd", "integral_limit", "d_alpha", "output_alpha"):
        suffix = _PID_PARAM_SUFFIXES.get(canonical, canonical)
        key = f"{label}_pid_{suffix}"
        value = cfg.get(key)
        try:
            data[canonical] = float(value)
        except Exception:
            data[canonical] = value
    if include_guidance:
        data["guidance"] = {k: _PID_PARAM_GUIDANCE.get(k, "") for k in _PID_PARAM_GUIDANCE}
    return data


def set_pid_params(mode, persist=True, reset=True, **params):
    """Update PID gains for the selected mode and optionally persist to disk."""
    if not params:
        raise ValueError("no PID parameters provided")
    label = _normalize_pid_mode(mode)
    cfg = _get_motor_cfg_ref()
    changes = {}
    for key, value in params.items():
        if key is None:
            continue
        canon = str(key).lower().replace(" ", "_")
        suffix = _PID_PARAM_SUFFIXES.get(canon)
        if suffix is None:
            raise ValueError("unsupported PID field: {}".format(key))
        cfg_key = f"{label}_pid_{suffix}"
        try:
            numeric = float(value)
        except Exception:
            raise ValueError("invalid value for {}: {}".format(key, value))
        if suffix in {"d_alpha", "output_alpha"}:
            if numeric < 0.0:
                numeric = 0.0
            if numeric > 1.0:
                numeric = 1.0
        changes[cfg_key] = numeric
    cfg.update(changes)
    motor = _get_motor_controller()
    if motor is not None and getattr(motor, "cfg", None) is cfg and reset:
        reset_fn = getattr(motor, "_reset_pid", None)
        if callable(reset_fn):
            try:
                reset_fn(label if label in {"power", "speed", "torque"} else None)
            except Exception:
                pass
    if persist:
        _save_motor_config(cfg)
    return get_pid_params(label)


def set_speed_target(kmh=None):
    """Force the speed controller to chase a fixed target (km/h) for tuning."""
    motor = _get_motor_controller()
    if motor is None:
        raise RuntimeError("motor controller not available")
    setter = getattr(motor, "set_speed_target_override", None)
    if not callable(setter):
        raise RuntimeError("speed target override not supported")
    value = setter(kmh)
    if value is None:
        print("[t] speed target override cleared; throttle ADC resumes control")
    else:
        print("[t] speed target override -> {:.1f} km/h".format(value))
    return value


# -------------- Main async --------------
async def _main_async():
    global _state, _ui, _dashboards, _dashboard_signals, _dashboard_trip, _dashboard_batt_select, _dashboard_batt_status, _dashboard_sys_batt, _dashboard_alarm, _page_button
    global _motor, _STOP_REQUESTED, _TASKS, _updown_buttons, _TRIP_COUNTER_INTERVAL_MS
    print("[t] _main_async: starting")
    _STOP_REQUESTED = False
    _TASKS.clear()
    motor_cfg = _load_motor_config()
    if _CONTROL_LOOP_DEBUG_OVERRIDE is not None:
        motor_cfg["monitor_control_enabled"] = bool(_CONTROL_LOOP_DEBUG_OVERRIDE)
    if _CONTROL_LOOP_DEBUG_PERIOD_MS is not None:
        try:
            motor_cfg["monitor_control_period_ms"] = max(200, int(_CONTROL_LOOP_DEBUG_PERIOD_MS))
        except Exception:
            motor_cfg["monitor_control_period_ms"] = 1000
    if _LOOP_TIMING_MONITOR_OVERRIDE is not None:
        motor_cfg["loop_timing_monitor_enabled"] = bool(_LOOP_TIMING_MONITOR_OVERRIDE)
    if _PID_TIMING_DEBUG_OVERRIDE is not None:
        motor_cfg["pid_timing_debug_enabled"] = bool(_PID_TIMING_DEBUG_OVERRIDE)
    if _PID_TIMING_DEBUG_PERIOD_MS is not None:
        try:
            motor_cfg["pid_timing_debug_period_ms"] = max(200, int(_PID_TIMING_DEBUG_PERIOD_MS))
        except Exception:
            motor_cfg["pid_timing_debug_period_ms"] = 1000
    print("[t] _main_async: motor config loaded")
    _motor = _create_motor_control(motor_cfg)
    print("[t] _main_async: motor control ready ->", type(_motor).__name__)
    _apply_control_loop_debug_pref(quiet=True)
    _apply_loop_timing_monitor_pref(quiet=True)
    _apply_pid_timing_debug_pref(quiet=True)
    try:
        trip_scale = float(motor_cfg.get("trip_pulse_to_meter", 0.1))
    except Exception:
        trip_scale = 0.1
    try:
        counter_id_cfg = int(motor_cfg.get("trip_counter_id", TRIP_COUNTER_ID))
    except Exception:
        counter_id_cfg = TRIP_COUNTER_ID
    try:
        counter_pin_cfg = int(motor_cfg.get("trip_counter_pin", TRIP_COUNTER_PIN))
    except Exception:
        counter_pin_cfg = TRIP_COUNTER_PIN
    try:
        counter_filter_cfg = int(motor_cfg.get("trip_counter_filter_ns", TRIP_COUNTER_FILTER_NS))
    except Exception:
        counter_filter_cfg = TRIP_COUNTER_FILTER_NS
    try:
        counter_interval_cfg = int(motor_cfg.get("trip_counter_interval_ms", TRIP_COUNTER_INTERVAL_MS))
    except Exception:
        counter_interval_cfg = TRIP_COUNTER_INTERVAL_MS
    try:
        _TRIP_COUNTER_INTERVAL_MS = int(counter_interval_cfg)
    except Exception:
        _TRIP_COUNTER_INTERVAL_MS = TRIP_COUNTER_INTERVAL_MS
    counter_edge_cfg = motor_cfg.get("trip_counter_edge", TRIP_COUNTER_EDGE)

    i2c = None
    try:
        i2c = make_i2c()
        print("[t] _main_async: I2C ready")
    except Exception as exc:
        print("[I2C] init error:", exc)

    if i2c is not None:
        try:
            init_dacs_zero(i2c)
        except Exception as exc:
            print("[DAC] zero error:", exc)
    else:
        print("[DAC] zero skipped (no I2C)")

    ui_instance = None
    dashboards = []
    dashboard_modes = None
    mode_screen_index = None
    dashboard_signals = None
    dashboard_trip = None
    dashboard_batt_select = None
    dashboard_batt_status = None
    dashboard_sys_batt = None
    dashboard_alarm = None
    initial_screen_index = None
    try:
        ui_instance = DisplayUI()
        print("[t] _main_async: UI init ok")
    except Exception as exc:
        print("[UI] init error:", exc)
    else:
        order_cfg = load_dashboard_order()
        setup = create_dashboards(ui_instance, trip_scale, order_cfg)
        dashboards = setup.get("dashboards", []) or []
        dashboard_modes = setup.get("dashboard_modes")
        mode_screen_index = setup.get("mode_screen_index")
        dashboard_signals = setup.get("dashboard_signals")
        dashboard_trip = setup.get("dashboard_trip")
        dashboard_batt_select = setup.get("dashboard_batt_select")
        dashboard_batt_status = setup.get("dashboard_batt_status")
        dashboard_sys_batt = setup.get("dashboard_sys_batt")
        dashboard_alarm = setup.get("dashboard_alarm")
        initial_screen_index = setup.get("initial_screen_index")
        if dashboards and initial_screen_index is None:
            initial_screen_index = 0

    _ui = ui_instance
    _dashboards = dashboards
    _dashboard_signals = dashboard_signals
    _dashboard_trip = dashboard_trip
    _dashboard_batt_select = dashboard_batt_select
    _dashboard_batt_status = dashboard_batt_status
    _dashboard_sys_batt = dashboard_sys_batt
    _dashboard_alarm = dashboard_alarm
    if _ui is not None:
        _show_status_screen(_ui, "Booting...", None)

    _state = AppState()
    print("[t] _main_async: AppState ready")
    _auto_disable_modem_on_boot()
    woke_from_main_wake = _woke_from_main_wake_pin()
    if woke_from_main_wake:
        try:
            snapshot = restore_trip_snapshot(_state)
            if snapshot:
                stamp = snapshot.get("stamp")
                stamp_txt = "{} ms".format(stamp) if stamp is not None else "unknown"
                print("[t] RTC resume: trip={} pulses, km_total={:.3f}, wh_total={:.3f} (stamp {})".format(
                    snapshot.get("trip_pulses", 0),
                    snapshot.get("km_total", 0.0) or 0.0,
                    snapshot.get("wh_total", 0.0) or 0.0,
                    stamp_txt,
                ))
        except Exception as exc:
            print("[t] RTC resume error:", exc)
    else:
        print("[t] RTC resume skipped (wake reason != GPIO{})".format(MAIN_WAKE_PIN))
    if _ui is not None:
        _show_status_screen(_ui, "Boot ready", _state)
    _state.motor_control = _motor
    try:
        _state.total_dashboards = len(_dashboards)
    except Exception:
        pass

    try:
        _track_task(asyncio.create_task(sys_pmu_task(_state)))
        print("[t] _main_async: sys_pmu task scheduled")
    except Exception as exc:
        print("[t] _main_async: sys_pmu unavailable", exc)

    schedule_sleep_guard(_state, MAIN_WAKE_PIN)

    if _dashboards and initial_screen_index is not None:
        try:
            screen_idx = int(initial_screen_index) % len(_dashboards)
        except Exception:
            screen_idx = 0
        _state.screen = screen_idx

    mode_controller = ThrottleModeController(
        state=_state,
        motor=_motor,
        motor_cfg=motor_cfg,
        dashboard_modes=dashboard_modes,
        screen_index=mode_screen_index,
    )
    mode_controller.initialize()

    bind_fn = getattr(_motor, "bind_state", None)
    if callable(bind_fn):
        try:
            bind_fn(_state)
            print("[t] _main_async: motor bound to state")
        except Exception as exc:
            print("[t] _main_async: bind_state error:", exc)
    else:
        print("[t] _main_async: motor lacks bind_state(); falling back to local ADCs")
    _state.init_local_adcs(force=True)
    print("[t] _main_async: local ADCs init attempted")

    # PageButton
    page_pin = make_input(PAGE_BTN_PIN)
    router = DashboardInputRouter(lambda: _dashboards, lambda: _state)
    page_btn = PageButton(
        page_pin,
        short=router.page_short,
        double=router.page_double,
        long=router.page_long,
        extra=router.page_extra,
    )
    _page_button = page_btn
    _track_task(asyncio.create_task(page_btn.task()))

    # Up/Down por ADC
    adc_ud = make_adc(UPDOWN_ADC_PIN)
    ud_btns = UpDownButtons(
        adc_ud,
        up_short=router.up_short,
        down_short=router.down_short,
        up_long=router.up_long,
        down_long=router.down_long,
        up_double=router.up_double,
        down_double=router.down_double,
        up_extra=router.up_extra,
        down_extra=router.down_extra,
    )
    _track_task(asyncio.create_task(ud_btns.task()))
    _updown_buttons = ud_btns

    # Hilo PR
    _start_pr_thread()

    try:
        _track_task(asyncio.create_task(auto_wake_pr_offload()))
    except Exception as exc:
        print("[t] auto wake scheduling failed:", exc)

    # Tareas
    if _dashboards:
        _track_task(asyncio.create_task(ui_task(_dashboards, _state, _get_ui_frame_interval)))
    _track_task(asyncio.create_task(integrator_task(_state, _get_integrator_interval)))
    _track_task(
        asyncio.create_task(
            trip_counter_task(
                _state,
                counter_id=counter_id_cfg,
                pin_num=counter_pin_cfg,
                pulse_to_meter=trip_scale,
                edge=counter_edge_cfg,
                filter_ns=counter_filter_cfg,
                interval_ms=counter_interval_cfg,
                interval_source=_get_trip_counter_interval,
            )
        )
    )
    print("[t] _main_async: trip counter task scheduled")
    motor_period = motor_cfg.get("update_period_ms")
    try:
        motor_period = int(motor_period) if motor_period is not None else None
    except Exception:
        motor_period = None
    run_fn = getattr(_motor, "run", None)
    if callable(run_fn):
        try:
            _track_task(asyncio.create_task(run_fn(period_ms=motor_period)))
            print("[t] _main_async: motor task scheduled")
        except Exception as exc:
            print("[Motor] schedule error:", exc)
    else:
        print("[t] _main_async: motor lacks run(); relying on local ADC readings only")
        _state.motor_control = None

    _track_task(asyncio.create_task(gc_task(_gc_task_config)))
    _track_task(asyncio.create_task(_uart_release_worker()))

    # Heartbeat solo si DEBUG=True
    if DEBUG:
        debug_on()

    try:
        while not _STOP_REQUESTED:
            await asyncio.sleep_ms(100)
    finally:
        debug_off()
        await _cancel_tracked_tasks()
        _motor = None
        _dashboards = []
        _dashboard_signals = None
        _dashboard_trip = None
        _dashboard_batt_select = None
        _dashboard_batt_status = None
        _dashboard_alarm = None
        _page_button = None
        _ui = None
        if _state is not None:
            try:
                _state.total_dashboards = 0
            except Exception:
                pass
        print("[t] _main_async: stop completed")


def _bg():
    global _RUNNING, _STOP_REQUESTED
    try:
        asyncio.run(_main_async())
    except Exception as e:
        print("Loop error:", e)
        try:
            sys.print_exception(e)
        except Exception:
            pass
        sleep_ms(500)
    finally:
        _RUNNING = False
        _STOP_REQUESTED = False


def start():
    global _RUNNING, _STOP_REQUESTED
    if _RUNNING:
        print("[t] start: already running")
        return False
    _STOP_REQUESTED = False
    _RUNNING = True
    try:
        if _BG_THREAD_STACK:
            try:
                _thread.stack_size(int(_BG_THREAD_STACK))
            except Exception as exc:
                print("[t] background stack size set error:", exc)
    except Exception:
        pass
    _thread.start_new_thread(_bg, ())
    return True


if AUTO_START:
    start()


async def sample_throttle_brake_async(samples=16, delay_ms=20):
    """Async helper to average throttle/brake ADC readings.

    When :class:`MotorControl` is active we reuse its ADCs to avoid
    duplicating hardware reads. Falling back to direct ADC access keeps the
    helper usable even if the controller is not running.
    """

    st = _state
    motor = getattr(st, "motor_control", None) if st is not None else None
    samples = max(1, int(samples))
    delay_ms = max(0, int(delay_ms))

    if motor is not None:
        try:
            return await motor.sample_voltages(samples=samples, delay_ms=delay_ms)
        except Exception:
            pass

    adc_th = getattr(st, "adc_throttle", None) if st is not None else None
    adc_br = getattr(st, "adc_brake", None) if st is not None else None
    if adc_th is None:
        try:
            adc_th = make_adc(ADC_THROTTLE_PIN)
            if st is not None:
                st.adc_throttle = adc_th
        except Exception:
            adc_th = None
    if adc_br is None:
        try:
            adc_br = make_adc(ADC_BRAKE_PIN)
            if st is not None:
                st.adc_brake = adc_br
        except Exception:
            adc_br = None

    read_th = getattr(adc_th, "read", None) or getattr(adc_th, "read_u16", None)
    read_br = getattr(adc_br, "read", None) or getattr(adc_br, "read_u16", None)
    if not callable(read_th) or not callable(read_br):
        return 0.0, 0.0

    acc_th = 0.0
    acc_br = 0.0
    count_th = 0
    count_br = 0
    for idx in range(samples):
        try:
            value_th = read_th()
            if isinstance(value_th, (int, float)):
                acc_th += float(value_th)
                count_th += 1
        except Exception:
            pass
        try:
            value_br = read_br()
            if isinstance(value_br, (int, float)):
                acc_br += float(value_br)
                count_br += 1
        except Exception:
            pass
        if delay_ms and idx + 1 < samples:
            await asyncio.sleep_ms(delay_ms)
    scale = 3.3 / 4095.0
    denom_th = count_th or samples
    denom_br = count_br or samples
    return (acc_th / float(denom_th)) * scale, (acc_br / float(denom_br)) * scale


def sample_throttle_brake(samples=16, delay_ms=20):
    """Blocking wrapper that runs :func:`sample_throttle_brake_async`.

    Safe to call from the REPL while the main UI loop is running in another
    thread—this spins a short-lived asyncio loop so other coroutines can keep
    scheduling between samples.
    """

    return asyncio.run(sample_throttle_brake_async(samples=samples, delay_ms=delay_ms))
