# t.py
# PR en hilo dedicado + UI/botones en uasyncio.
# Cambios:
# - API de consola:
#     import t; t.print_status()
import _thread
import uasyncio as asyncio
from time import sleep_ms, ticks_ms, ticks_diff
import sys

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
    TRIP_COUNTER_ID,
    TRIP_COUNTER_PIN,
    TRIP_COUNTER_FILTER_NS,
    TRIP_COUNTER_EDGE,
    TRIP_COUNTER_INTERVAL_MS,
    make_i2c,
    make_adc,
    make_input,
)

from UI_helpers import (
    DisplayUI,
    DashboardLayout,
    DashboardSignals,
    DashboardTrip,
    DashboardBattSelect,
    DashboardBattStatus,
    DashboardModes,
)
from app_state import AppState, THROTTLE_MODES_DEFAULT
import buttons as _buttons_mod
from buttons import PageButton, UpDownButtons
import fonts
from runtime.motor import (
    MOTOR_CONFIG_FILE,
    MOTOR_DEFAULTS,
    compute_output_voltages,
    create_motor_control,
    load_motor_config,
    save_motor_config,
)
from runtime.tasks import ui_task, integrator_task, trip_counter_task, heartbeat_task
import runtime.phaserunner_worker as pr_bridge
from runtime.hardware import init_dacs_zero
from UI_helpers.writer import Writer

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

_PR_FAST_MS = 100
_PR_SLOW_MS = 2000
_UI_FRAME_MS = 80
_INTEGRATOR_MS = 200
_TRIP_COUNTER_INTERVAL_MS = TRIP_COUNTER_INTERVAL_MS
DASHBOARD_ORDER_FILE = "dashboard_order.json"


def _load_dashboard_order():
    try:
        print("[t] dashboard order: loading {}".format(DASHBOARD_ORDER_FILE))
    except Exception:
        pass
    try:
        with open(DASHBOARD_ORDER_FILE, "r") as fp:
            raw = fp.read()
    except Exception:
        try:
            print("[t] dashboard order: file missing")
        except Exception:
            pass
        return {}
    if not raw:
        try:
            print("[t] dashboard order: empty file")
        except Exception:
            pass
        return {}
    result = {}
    def _parse_list(blob, key):
        token = '"{}"'.format(key)
        idx = blob.find(token)
        if idx < 0:
            return None
        idx = blob.find('[', idx)
        if idx < 0:
            return None
        depth = 0
        end = -1
        for pos in range(idx, len(blob)):
            ch = blob[pos]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = pos
                    break
        if end < 0:
            return None
        body = blob[idx + 1 : end]
        items = []
        for part in body.split(','):
            item = part.strip()
            if not item:
                continue
            if item[0] in ('"', "'") and item[-1] == item[0]:
                item = item[1:-1]
            items.append(item.strip())
        return items if items else None

    def _parse_string(blob, key):
        token = '"{}"'.format(key)
        idx = blob.find(token)
        if idx < 0:
            return ""
        idx = blob.find(':', idx)
        if idx < 0:
            return ""
        idx += 1
        length = len(blob)
        while idx < length and blob[idx] in " \t\r\n":
            idx += 1
        if idx >= length:
            return ""
        quote = blob[idx]
        if quote not in ('"', "'"):
            return ""
        idx += 1
        end = blob.find(quote, idx)
        if end < 0:
            return ""
        return blob[idx:end].strip()

    order_items = _parse_list(raw, "order")
    if order_items:
        cleaned = []
        for name in order_items:
            try:
                key = str(name).strip().lower()
            except Exception:
                continue
            if not key or key in cleaned:
                continue
            cleaned.append(key)
        if cleaned:
            result["order"] = cleaned

    start_item = _parse_string(raw, "start")
    if start_item:
        try:
            start_key = str(start_item).strip().lower()
        except Exception:
            start_key = ""
        if start_key:
            result["start"] = start_key
    try:
        print("[t] dashboard order: loaded", result)
    except Exception:
        pass
    return result


def _track_task(task):
    if task is None:
        return None
    try:
        _TASKS.append(task)
    except Exception:
        pass
    return task


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


def _font_text_width(font_mod, text):
    width = 0
    for ch in text:
        try:
            _, _, advance = font_mod.get_ch(ch)
        except Exception:
            advance = 0
        width += advance
    return width


def _show_boot_message(ui_display, lines=None):
    if ui_display is None:
        return
    if not lines:
        lines = ["eBikeWatch", "Booting..."]
    try:
        font_mod = fonts.load("Font00_24")
    except Exception:
        font_mod = None
    if font_mod is None:
        try:
            ui_display.draw_boot(lines[0] if lines else "eBikeWatch")
        except Exception:
            pass
        return

    framebuf = ui_display.display.framebuf
    writer = Writer(framebuf, font_mod, verbose=False)
    writer.setcolor(0xFFFF, 0x0000)
    writer.set_clip(col_clip=True, wrap=False)

    try:
        ui_display.display.fill(0)
    except Exception:
        ui_display.clear()

    height = ui_display.display.height
    font_height = font_mod.height()
    total_height = font_height * len(lines)
    y = (height - total_height) // 2
    if y < 0:
        y = 0

    for line in lines:
        text = (line or "")[:24]
        width = _font_text_width(font_mod, text)
        x = (ui_display.display.width - width) // 2
        if x < 0:
            x = 0
        Writer.set_textpos(framebuf, y, x)
        writer.printstring(text)
        y += font_height

    ui_display.display.show()


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


# -------------- Main async --------------
async def _main_async():
    global _state, _ui, _dashboards, _dashboard_signals, _dashboard_trip, _dashboard_batt_select, _dashboard_batt_status, _page_button
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
    print("[t] _main_async: motor config loaded")
    _motor = _create_motor_control(motor_cfg)
    print("[t] _main_async: motor control ready ->", type(_motor).__name__)
    _apply_control_loop_debug_pref(quiet=True)
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
    initial_screen_index = None
    try:
        ui_instance = DisplayUI()
        print("[t] _main_async: UI init ok")
    except Exception as exc:
        print("[UI] init error:", exc)
    else:
        order_cfg = _load_dashboard_order()
        order_data = order_cfg.get("order")
        if isinstance(order_data, list):
            requested_order = list(order_data)
        else:
            requested_order = []
        start_name = order_cfg.get("start")
        default_order = ["layout", "battery_select", "battery_status", "trip", "modes", "signals"]
        available_factories = {
            "layout": lambda: DashboardLayout(ui_instance),
            "battery_select": lambda: DashboardBattSelect(ui_instance),
            "battery_status": lambda: DashboardBattStatus(ui_instance),
            "trip": lambda: DashboardTrip(ui_instance, pulse_to_meter=trip_scale),
            "modes": lambda: DashboardModes(ui_instance),
            "signals": lambda: DashboardSignals(ui_instance),
        }
        added = set()

        def _create_dashboard(key):
            factory = available_factories.get(key)
            if factory is None:
                print("[UI] unknown dashboard:", key)
                return None
            try:
                print("[UI] dashboard create ->", key)
                dash_obj = factory()
                print("[UI] dashboard ready <-", key)
                return dash_obj
            except Exception as factory_exc:
                print("[UI] dashboard {} init error:".format(key), factory_exc)
                return None

        def _register_dashboard(dash, key):
            nonlocal dashboard_modes, mode_screen_index, dashboard_signals, dashboard_trip, dashboard_batt_select, dashboard_batt_status, initial_screen_index
            idx = len(dashboards)
            dashboards.append(dash)
            setter = getattr(dash, "set_screen_index", None)
            if callable(setter):
                try:
                    setter(idx)
                except Exception:
                    pass
            if isinstance(dash, DashboardModes):
                dashboard_modes = dash
                mode_screen_index = idx
            elif isinstance(dash, DashboardSignals):
                dashboard_signals = dash
            elif isinstance(dash, DashboardTrip):
                dashboard_trip = dash
            elif isinstance(dash, DashboardBattSelect):
                dashboard_batt_select = dash
            elif isinstance(dash, DashboardBattStatus):
                dashboard_batt_status = dash
            if start_name and key == start_name and initial_screen_index is None:
                initial_screen_index = idx
            if hasattr(dash, "request_full_refresh"):
                dash.request_full_refresh()

        for key in requested_order:
            try:
                key_norm = str(key).strip().lower()
            except Exception:
                continue
            if not key_norm or key_norm in added:
                continue
            dash_obj = _create_dashboard(key_norm)
            if dash_obj is None:
                continue
            _register_dashboard(dash_obj, key_norm)
            added.add(key_norm)

        for key in default_order:
            if key in added:
                continue
            dash_obj = _create_dashboard(key)
            if dash_obj is None:
                continue
            _register_dashboard(dash_obj, key)
            added.add(key)

        for key in available_factories.keys():
            if key in added:
                continue
            dash_obj = _create_dashboard(key)
            if dash_obj is None:
                continue
            _register_dashboard(dash_obj, key)
            added.add(key)

        if dashboards and initial_screen_index is None:
            initial_screen_index = 0

    _ui = ui_instance
    _dashboards = dashboards
    _dashboard_signals = dashboard_signals
    _dashboard_trip = dashboard_trip
    _dashboard_batt_select = dashboard_batt_select
    _dashboard_batt_status = dashboard_batt_status
    if _ui is not None:
        _show_boot_message(_ui, ["eBikeWatch", "Booting..."])

    _state = AppState()
    print("[t] _main_async: AppState ready")
    _state.motor_control = _motor
    try:
        _state.total_dashboards = len(_dashboards)
    except Exception:
        pass

    if _dashboards and initial_screen_index is not None:
        try:
            screen_idx = int(initial_screen_index) % len(_dashboards)
        except Exception:
            screen_idx = 0
        _state.screen = screen_idx

    _mode_save_pending = None
    _mode_save_task = None
    _mode_confirm_guard = False

    async def _persist_mode_save_worker():
        nonlocal _mode_save_pending, _mode_save_task
        try:
            while True:
                pending_mode = _mode_save_pending
                if pending_mode is None:
                    break
                _mode_save_pending = None
                await asyncio.sleep_ms(50)
                try:
                    if not _save_motor_config(motor_cfg):
                        print("[t] throttle mode persist failed")
                except Exception as exc:
                    print("[t] throttle mode persist error:", exc)
        finally:
            _mode_save_task = None

    def _schedule_mode_save():
        nonlocal _mode_save_task
        if _mode_save_pending is None:
            return
        if _mode_save_task is None:
            task = asyncio.create_task(_persist_mode_save_worker())
            _mode_save_task = task
            _track_task(task)

    def _normalize_mode_label(value):
        try:
            label = str(value or "").strip().lower()
        except Exception:
            return ""
        if label in {"open", "open_loop", "raw"}:
            return "direct"
        return label

    def _prioritize_modes(sequence):
        ordered = []
        for item in sequence:
            norm = _normalize_mode_label(item)
            if norm and norm not in ordered:
                ordered.append(norm)
        for fallback in THROTTLE_MODES_DEFAULT:
            if fallback not in ordered:
                ordered.append(fallback)
        if "direct" in ordered:
            ordered.insert(0, ordered.pop(ordered.index("direct")))
        else:
            ordered.insert(0, "direct")
        return ordered

    modes_available = _prioritize_modes(getattr(_state, "throttle_modes", []))
    active_mode_cfg = _normalize_mode_label(motor_cfg.get("throttle_mode"))
    if not active_mode_cfg:
        active_mode_cfg = modes_available[0] if modes_available else "direct"
    if active_mode_cfg not in modes_available:
        modes_available.append(active_mode_cfg)
        modes_available = _prioritize_modes(modes_available)
    active_idx = modes_available.index(active_mode_cfg) if active_mode_cfg in modes_available else 0
    active_mode_cfg = modes_available[active_idx] if modes_available else "direct"
    _state.throttle_modes = modes_available
    _state.throttle_mode_index = active_idx
    _state.throttle_mode_active = active_mode_cfg
    _state.throttle_mode_candidate = active_mode_cfg
    try:
        _state.throttle_mode_confirmed_ms = int(ticks_ms() or 0)
    except Exception:
        _state.throttle_mode_confirmed_ms = 0
    setter = getattr(_motor, "set_throttle_mode", None)
    if callable(setter):
        try:
            setter(active_mode_cfg)
        except Exception:
            pass
    else:
        try:
            cfg_obj = getattr(_motor, "cfg", None)
            if isinstance(cfg_obj, dict):
                cfg_obj["throttle_mode"] = active_mode_cfg
        except Exception:
            pass
    motor_cfg["throttle_mode"] = active_mode_cfg
    if dashboard_modes is not None:
        dashboard_modes.request_full_refresh()

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

    def _dispatch_dashboard_event(event, **kwargs):
        if not _dashboards:
            return False
        idx = getattr(_state, "screen", 0)
        try:
            idx = int(idx)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(_dashboards):
            return False
        dash = _dashboards[idx]
        handler = getattr(dash, "handle_event", None)
        if not callable(handler):
            return False
        try:
            result = handler(event, _state, **kwargs)
        except Exception as exc:
            print("[UI] event error:", exc)
            return True
        handled = False
        refresh_all = False
        refresh_self = False
        switch_screen = None
        message = None
        if isinstance(result, dict):
            handled = bool(result.get("handled", True))
            refresh_all = bool(result.get("refresh_all"))
            refresh_self = bool(result.get("refresh_self"))
            switch_screen = result.get("switch_screen")
            message = result.get("message")
        else:
            handled = bool(result)
        if message:
            print(message)
        if handled and switch_screen is not None and _dashboards:
            try:
                target = int(switch_screen)
            except Exception:
                target = None
            else:
                count = len(_dashboards)
                if count > 0 and target is not None:
                    target = target % count
                    _state.screen = target
                    target_dash = _dashboards[target]
                    if hasattr(target_dash, "request_full_refresh"):
                        target_dash.request_full_refresh()
        if refresh_all and _dashboards:
            for dash_item in _dashboards:
                if hasattr(dash_item, "request_full_refresh"):
                    dash_item.request_full_refresh()
        elif refresh_self and hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()
        return handled

    def _change_screen(delta):
        if not _dashboards:
            return
        count = len(_dashboards)
        if count <= 0:
            return
        current = getattr(_state, "screen", 0)
        try:
            current = int(current)
        except Exception:
            current = 0
        target = (current + delta) % count
        if target == current:
            return
        _state.screen = target
        dash = _dashboards[target]
        if hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()

    def on_page_short():
        if _dispatch_dashboard_event("page_short"):
            return

    def on_page_double():
        if _dispatch_dashboard_event("page_double"):
            return
        on_page_short()

    def on_page_long():
        if _dispatch_dashboard_event("page_long"):
            return

    def on_page_extra():
        _dispatch_dashboard_event("page_extra")

    page_btn = PageButton(page_pin, short=on_page_short, double=on_page_double, long=on_page_long, extra=on_page_extra)
    _page_button = page_btn
    _track_task(asyncio.create_task(page_btn.task()))

    # Up/Down por ADC
    adc_ud = make_adc(UPDOWN_ADC_PIN)
    def _apply_mode_delta(delta):
        if mode_screen_index is None or _state.screen != mode_screen_index:
            return
        modes = getattr(_state, "throttle_modes", [])
        if not modes:
            return
        current = getattr(_state, "throttle_mode_index", 0)
        try:
            current = int(current)
        except Exception:
            current = 0
        new_idx = (current + delta) % len(modes)
        if getattr(_buttons_mod, "DEBUG", False):
            print("[Mode] delta={} {}->{}".format(delta, current, new_idx))
        _state.throttle_mode_index = new_idx
        try:
            mode_value = modes[new_idx]
        except Exception:
            mode_value = modes[new_idx] if modes else "direct"
        mode_norm = _normalize_mode_label(mode_value) or "direct"
        try:
            modes[new_idx] = mode_norm
        except Exception:
            pass
        _state.throttle_mode_candidate = mode_norm
        _state.throttle_mode_confirmed_ms = 0
        if dashboard_modes is not None:
            dashboard_modes.request_full_refresh()

    def _confirm_mode_selection():
        nonlocal _mode_save_pending, _mode_confirm_guard
        if _mode_confirm_guard:
            return False
        if mode_screen_index is None or _state.screen != mode_screen_index:
            return False
        modes = getattr(_state, "throttle_modes", [])
        if not modes:
            return False
        _mode_confirm_guard = True
        try:
            idx = getattr(_state, "throttle_mode_index", 0)
            try:
                idx = int(idx) % len(modes)
            except Exception:
                idx = 0
            mode = modes[idx]
            mode_norm = _normalize_mode_label(mode) or "direct"
            try:
                modes[idx] = mode_norm
            except Exception:
                pass
            _state.throttle_mode_index = idx
            _state.throttle_mode_candidate = mode_norm
            _state.throttle_mode_active = mode_norm
            try:
                confirm_stamp = int(ticks_ms() or 0)
            except Exception:
                confirm_stamp = 0
            _state.throttle_mode_confirmed_ms = confirm_stamp
            setter_local = getattr(_motor, "set_throttle_mode", None)
            if callable(setter_local):
                try:
                    setter_local(mode_norm)
                except Exception as exc:
                    print("[Motor] throttle_mode set error:", exc)
            else:
                try:
                    cfg_obj = getattr(_motor, "cfg", None)
                    if isinstance(cfg_obj, dict):
                        cfg_obj["throttle_mode"] = mode_norm
                except Exception:
                    pass
            motor_cfg["throttle_mode"] = mode_norm
            print("[t] throttle mode ->", mode_norm)
            _mode_save_pending = mode_norm
            _schedule_mode_save()
            return True
        finally:
            _mode_confirm_guard = False

    if dashboard_modes is not None:
        dashboard_modes.set_handlers(on_move=_apply_mode_delta, on_confirm=_confirm_mode_selection)

    def on_up_short():
        if _dispatch_dashboard_event("up_short"):
            return
        _change_screen(1)

    def on_down_short():
        if _dispatch_dashboard_event("down_short"):
            return
        _change_screen(-1)

    def on_up_long():
        _dispatch_dashboard_event("up_long")

    def on_down_long():
        _dispatch_dashboard_event("down_long")

    def on_up_double():
        if _dispatch_dashboard_event("up_double"):
            return

    def on_down_double():
        if _dispatch_dashboard_event("down_double"):
            return

    def on_up_extra():
        _dispatch_dashboard_event("up_extra")

    def on_down_extra():
        _dispatch_dashboard_event("down_extra")

    ud_btns = UpDownButtons(
        adc_ud,
        up_short=on_up_short,
        down_short=on_down_short,
        up_long=on_up_long,
        down_long=on_down_long,
        up_double=on_up_double,
        down_double=on_down_double,
        up_extra=on_up_extra,
        down_extra=on_down_extra,
    )
    _track_task(asyncio.create_task(ud_btns.task()))
    _updown_buttons = ud_btns

    # Hilo PR
    _start_pr_thread()

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
