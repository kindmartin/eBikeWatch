"""UI management helpers split from t.py."""

import uasyncio as asyncio
from time import ticks_ms

import buttons as _buttons_mod
from app_state import THROTTLE_MODES_DEFAULT
from runtime.motor import save_motor_config
from UI_helpers import (
    DashboardLayout,
    DashboardSignals,
    DashboardTrip,
    DashboardBattSelect,
    DashboardBattStatus,
    DashboardModes,
    DashboardSysBatt,
    DashboardAlarm,
)

DASHBOARD_ORDER_FILE = "dashboard_order.json"


class DashboardInputRouter:
    """Route dashboard events using external getters for dashboards/state."""

    def __init__(self, dashboards_getter, state_getter):
        self._dashboards_getter = dashboards_getter
        self._state_getter = state_getter

    def _dashboards(self):
        dashboards = self._dashboards_getter()
        return dashboards or []

    def _state(self):
        return self._state_getter()

    def dispatch(self, event, **kwargs):
        dashboards = self._dashboards()
        state = self._state()
        if not dashboards or state is None:
            return False
        try:
            idx = int(getattr(state, "screen", 0) or 0)
        except Exception:
            idx = 0
        count = len(dashboards)
        if count <= 0:
            return False
        idx %= count
        dash = dashboards[idx]
        handler = getattr(dash, "handle_event", None)
        if not callable(handler):
            return False
        try:
            result = handler(event, state, **kwargs)
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
        if handled and switch_screen is not None and dashboards:
            try:
                target = int(switch_screen)
            except Exception:
                target = None
            if target is not None and len(dashboards):
                target %= len(dashboards)
                state.screen = target
                target_dash = dashboards[target]
                if hasattr(target_dash, "request_full_refresh"):
                    target_dash.request_full_refresh()
        if refresh_all and dashboards:
            for dash_item in dashboards:
                if hasattr(dash_item, "request_full_refresh"):
                    dash_item.request_full_refresh()
        elif refresh_self and hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()
        return handled

    def change_screen(self, delta):
        dashboards = self._dashboards()
        state = self._state()
        if not dashboards or state is None:
            return
        count = len(dashboards)
        if count <= 0:
            return
        try:
            current = int(getattr(state, "screen", 0) or 0)
        except Exception:
            current = 0
        target = (current + delta) % count
        if target == current:
            return
        state.screen = target
        dash = dashboards[target]
        if hasattr(dash, "request_full_refresh"):
            dash.request_full_refresh()

    def page_short(self):
        if self.dispatch("page_short"):
            return

    def page_double(self):
        if self.dispatch("page_double"):
            return
        self.page_short()

    def page_long(self):
        if self.dispatch("page_long"):
            return

    def page_extra(self):
        self.dispatch("page_extra")

    def up_short(self):
        if self.dispatch("up_short"):
            return
        self.change_screen(1)

    def down_short(self):
        if self.dispatch("down_short"):
            return
        self.change_screen(-1)

    def up_long(self):
        self.dispatch("up_long")

    def down_long(self):
        self.dispatch("down_long")

    def up_double(self):
        if self.dispatch("up_double"):
            return

    def down_double(self):
        if self.dispatch("down_double"):
            return

    def up_extra(self):
        self.dispatch("up_extra")

    def down_extra(self):
        self.dispatch("down_extra")


class ThrottleModeController:
    """Manage throttle mode selection without nested closures."""

    def __init__(self, state, motor, motor_cfg, dashboard_modes, screen_index):
        self.state = state
        self.motor = motor
        self.motor_cfg = motor_cfg
        self.dashboard = dashboard_modes
        self.screen_index = screen_index
        self.pending_mode = None
        self.save_task = None
        self.confirm_guard = False

    @staticmethod
    def _normalize_mode_label(value):
        try:
            label = str(value or "").strip().lower()
        except Exception:
            label = ""
        if label in {"open", "open_loop", "raw"}:
            return "direct"
        return label

    @staticmethod
    def _prioritize_modes(sequence):
        ordered = []
        for item in sequence:
            norm = ThrottleModeController._normalize_mode_label(item)
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

    def initialize(self):
        state = self.state
        modes_available = self._prioritize_modes(getattr(state, "throttle_modes", []))
        active_mode_cfg = self._normalize_mode_label(self.motor_cfg.get("throttle_mode"))
        if not active_mode_cfg:
            active_mode_cfg = modes_available[0] if modes_available else "direct"
        if active_mode_cfg not in modes_available:
            modes_available.append(active_mode_cfg)
            modes_available = self._prioritize_modes(modes_available)
        active_idx = modes_available.index(active_mode_cfg) if active_mode_cfg in modes_available else 0
        active_mode_cfg = modes_available[active_idx] if modes_available else "direct"
        state.throttle_modes = modes_available
        state.throttle_mode_index = active_idx
        state.throttle_mode_active = active_mode_cfg
        state.throttle_mode_candidate = active_mode_cfg
        try:
            state.throttle_mode_confirmed_ms = int(ticks_ms() or 0)
        except Exception:
            state.throttle_mode_confirmed_ms = 0
        setter = getattr(self.motor, "set_throttle_mode", None)
        if callable(setter):
            try:
                setter(active_mode_cfg)
            except Exception:
                pass
        else:
            cfg_obj = getattr(self.motor, "cfg", None)
            if isinstance(cfg_obj, dict):
                cfg_obj["throttle_mode"] = active_mode_cfg
        self.motor_cfg["throttle_mode"] = active_mode_cfg
        if self.dashboard is not None:
            self.dashboard.request_full_refresh()
            self.dashboard.set_handlers(on_move=self.apply_delta, on_confirm=self.confirm_selection)

    def apply_delta(self, delta):
        if self.screen_index is None:
            return
        state = self.state
        if getattr(state, "screen", None) != self.screen_index:
            return
        modes = getattr(state, "throttle_modes", [])
        if not modes:
            return
        try:
            current = int(getattr(state, "throttle_mode_index", 0) or 0)
        except Exception:
            current = 0
        new_idx = (current + int(delta)) % len(modes)
        if getattr(_buttons_mod, "DEBUG", False):
            print("[Mode] delta={} {}->{}".format(delta, current, new_idx))
        state.throttle_mode_index = new_idx
        try:
            mode_value = modes[new_idx]
        except Exception:
            mode_value = modes[new_idx] if modes else "direct"
        mode_norm = self._normalize_mode_label(mode_value) or "direct"
        try:
            modes[new_idx] = mode_norm
        except Exception:
            pass
        state.throttle_mode_candidate = mode_norm
        state.throttle_mode_confirmed_ms = 0
        if self.dashboard is not None:
            self.dashboard.request_full_refresh()

    async def _persist_mode_save_worker(self):
        try:
            while self.pending_mode is not None:
                pending_mode = self.pending_mode
                self.pending_mode = None
                try:
                    save_motor_config(self.motor_cfg)
                    print("[Mode] default throttle -> {}".format(pending_mode))
                except Exception as exc:  # type: ignore[name-defined]
                    print("[Mode] save error:", exc)
        finally:
            self.save_task = None

    def confirm_selection(self):
        state = self.state
        modes = getattr(state, "throttle_modes", [])
        if not modes:
            return False
        try:
            idx = int(getattr(state, "throttle_mode_index", 0) or 0)
        except Exception:
            idx = 0
        idx %= len(modes)
        mode = modes[idx]
        mode_norm = self._normalize_mode_label(mode) or "direct"
        if getattr(state, "throttle_mode_active", None) == mode_norm and self.confirm_guard:
            return False
        state.throttle_mode_active = mode_norm
        state.throttle_mode_candidate = mode_norm
        state.throttle_mode_confirmed_ms = ticks_ms()
        setter = getattr(self.motor, "set_throttle_mode", None)
        if callable(setter):
            try:
                setter(mode_norm)
            except Exception as exc:
                print("[Mode] apply error:", exc)
        self.motor_cfg["throttle_mode"] = mode_norm
        self.pending_mode = mode_norm
        if self.save_task is None:
            loop = asyncio.get_event_loop()
            self.save_task = loop.create_task(self._persist_mode_save_worker())
        if self.dashboard is not None:
            self.dashboard.request_full_refresh()
        self.confirm_guard = True
        return True


def load_dashboard_order(file_path=DASHBOARD_ORDER_FILE):
    try:
        print("[t] dashboard order: loading {}".format(file_path))
    except Exception:
        pass
    try:
        with open(file_path, "r") as fp:
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


def create_dashboards(ui_instance, trip_scale, order_cfg=None):
    setup = {
        "dashboards": [],
        "dashboard_modes": None,
        "mode_screen_index": None,
        "dashboard_signals": None,
        "dashboard_trip": None,
        "dashboard_batt_select": None,
        "dashboard_batt_status": None,
        "dashboard_sys_batt": None,
        "dashboard_alarm": None,
        "initial_screen_index": None,
    }
    if ui_instance is None:
        return setup
    order_cfg = order_cfg or {}
    order_data = order_cfg.get("order")
    requested_order = list(order_data) if isinstance(order_data, list) else []
    start_name = order_cfg.get("start")
    default_order = [
        "layout",
        "battery_select",
        "battery_status",
        "trip",
        "modes",
        "signals",
        "sysbatt",
        "alarm",
    ]
    available_factories = {
        "layout": lambda: DashboardLayout(ui_instance),
        "battery_select": lambda: DashboardBattSelect(ui_instance),
        "battery_status": lambda: DashboardBattStatus(ui_instance),
        "trip": lambda: DashboardTrip(ui_instance, pulse_to_meter=trip_scale),
        "modes": lambda: DashboardModes(ui_instance),
        "signals": lambda: DashboardSignals(ui_instance),
        "sysbatt": lambda: DashboardSysBatt(ui_instance),
        "alarm": lambda: DashboardAlarm(ui_instance),
    }
    dashboards = []
    added = set()
    metadata = setup.copy()

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
        nonlocal metadata
        idx = len(dashboards)
        dashboards.append(dash)
        setter = getattr(dash, "set_screen_index", None)
        if callable(setter):
            try:
                setter(idx)
            except Exception:
                pass
        if isinstance(dash, DashboardModes):
            metadata["dashboard_modes"] = dash
            metadata["mode_screen_index"] = idx
        elif isinstance(dash, DashboardSignals):
            metadata["dashboard_signals"] = dash
        elif isinstance(dash, DashboardTrip):
            metadata["dashboard_trip"] = dash
        elif isinstance(dash, DashboardBattSelect):
            metadata["dashboard_batt_select"] = dash
        elif isinstance(dash, DashboardBattStatus):
            metadata["dashboard_batt_status"] = dash
        elif isinstance(dash, DashboardSysBatt):
            metadata["dashboard_sys_batt"] = dash
        elif isinstance(dash, DashboardAlarm):
            metadata["dashboard_alarm"] = dash
        if start_name and key == start_name and metadata.get("initial_screen_index") is None:
            metadata["initial_screen_index"] = idx
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

    if dashboards and metadata.get("initial_screen_index") is None:
        metadata["initial_screen_index"] = 0

    metadata["dashboards"] = dashboards
    return metadata
