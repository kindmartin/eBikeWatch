"""Battery pack selection and configuration dashboard."""

import bats
import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000

_PADDING_X = 8
_ROW_GAP = 8
_LIST_PADDING_Y = 10
_STATUS_GAP = 4
_MAX_VISIBLE = 4

_CREATE_FIELDS = ("cells_series", "parallel", "cell_capacity_mAh")
_FIELD_STEPS = {
    "cells_series": 1,
    "parallel": 1,
    "cell_capacity_mAh": 100,
}
_FIELD_LIMITS = {
    "cells_series": (1, 32),
    "parallel": (1, 10),
    "cell_capacity_mAh": (500, 20000),
}


class DashboardBattSelect(DashboardBase):
    """Interactive dashboard to select or create battery packs."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="BATT SEL", sep_color=0x07E0)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        try:
            self.font_small = fonts.load("sevenSegment_20")
        except Exception:
            self.font_small = fonts.load("Font00_24")

        try:
            self.font_mode = fonts.load("sevenSegment_30")
        except Exception:
            self.font_mode = self.font_small

        self.writer_mode = Writer(framebuf, self.font_mode, verbose=False)
        self.writer_mode.setcolor(FG_COLOR, BG_COLOR)
        self.writer_mode.set_clip(col_clip=True, wrap=False)

        self.writer_small = Writer(framebuf, self.font_small, verbose=False)
        self.writer_small.setcolor(FG_COLOR, BG_COLOR)
        self.writer_small.set_clip(col_clip=True, wrap=False)

        self._entered = False
        self._mode = "list"
        self._selection = 0
        self._create_field = 0
        self._create_values = {
            "cells_series": 21,
            "parallel": 1,
            "cell_capacity_mAh": 4500.0,
        }
        self._needs_refresh = True
        self._last_snapshot = None

    # ---------- DashboardBase overrides ----------
    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_refresh = True
        self._last_snapshot = None

    def handle_event(self, event, state, **kwargs):
        if event == "page_double":
            event = "page_short"

        if event == "page_short":
            if self._entered:
                if self._mode == "create":
                    self._mode = "list"
                    self._create_field = 0
                    self._sync_selection(state)
                else:
                    self._sync_selection(state)
                self._entered = False
            else:
                self._entered = True
                if self._mode != "create":
                    self._sync_selection(state)
            self._mark_dirty()
            return {"handled": True, "refresh_self": True}

        if event == "page_long":
            if not self._entered:
                return False
            if self._mode == "list":
                return self._activate_selection(state)
            if self._mode == "create":
                self._advance_field()
                self._mark_dirty()
                return {"handled": True, "refresh_self": True}
            return False

        if event == "page_extra":
            if not self._entered:
                return False
            if self._mode == "create":
                return self._save_new_pack(state)
            return False

        if event == "up_short":
            if not self._entered:
                return False
            if self._mode == "list":
                return self._move_selection(state, -1)
            if self._mode == "create":
                self._adjust_field(1)
                self._mark_dirty()
                return {"handled": True, "refresh_self": True}
            return False

        if event == "down_short":
            if not self._entered:
                return False
            if self._mode == "list":
                return self._move_selection(state, 1)
            if self._mode == "create":
                self._adjust_field(-1)
                self._mark_dirty()
                return {"handled": True, "refresh_self": True}
            return False

        return False

    # ---------- Rendering ----------
    def draw(self, state):
        names = self._pack_names()
        if not names:
            names = ["CREATE NEW"]
        max_index = len(names) - 1
        if self._selection > max_index:
            self._selection = max_index
        if self._selection < 0:
            self._selection = 0

        if not self._entered and self._mode == "list":
            self._sync_selection(state)

        current_name = self._current_pack_name(state)
        pack = getattr(state, "battery_pack", {}) or {}
        pack_info = self._format_pack_info(pack)
        create_snapshot = (
            round(self._create_values.get("cells_series", 0)),
            round(self._create_values.get("parallel", 0)),
            round(self._create_values.get("cell_capacity_mAh", 0)),
            self._create_field,
        )
        snapshot = (
            tuple(names),
            self._selection,
            self._entered,
            self._mode,
            current_name,
            pack_info,
            create_snapshot,
        )
        if not self._needs_refresh and snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self._needs_refresh = False

        self.ensure_header(force=True)
        lcd = self.lcd
        top = self.header_height
        lcd.fill_rect(0, top, lcd.width, lcd.height - top, BG_COLOR)

        info_y = top + 2
        self._draw_text(self.writer_small, self.font_small, "CUR {}".format(current_name), _PADDING_X, info_y)
        info_y += self.font_small.height()
        self._draw_text(self.writer_small, self.font_small, pack_info, _PADDING_X, info_y)

        content_y = info_y + self.font_small.height() + _ROW_GAP

        if self._mode == "create":
            self._draw_create_editor(content_y)
            current_field = _CREATE_FIELDS[self._create_field]
            field_label = self._field_label(current_field)
            value_text = self._field_value_text(current_field, self._create_values[current_field])
            status_label = "{} {}".format(field_label, value_text)
            instructions = "UP/DN +/-  PAGE LONG NEXT  EXTRA SAVE  SH EXIT"
        else:
            status_label, instructions = self._draw_list(names, content_y, current_name)

        self._draw_status_lines(status_label, instructions)
        self.lcd.show()

    def _draw_list(self, names, start_y, current_name):
        lcd = self.lcd
        list_bottom = lcd.height - (self.font_small.height() * 2 + _STATUS_GAP + 4)
        total = len(names)
        if total <= _MAX_VISIBLE:
            start = 0
        else:
            half = _MAX_VISIBLE // 2
            start = self._selection - half
            if start < 0:
                start = 0
            end = start + _MAX_VISIBLE
            if end > total:
                start = total - _MAX_VISIBLE
        current_upper = current_name.upper()
        display_current = current_upper or "-"
        if display_current == "CREATE NEW":
            display_current = "CREATE"
        y = start_y
        for idx in range(start, min(start + _MAX_VISIBLE, total)):
            label = names[idx].upper()[:16]
            if y + self.font_mode.height() > list_bottom:
                break
            width = self._text_width(self.font_mode, label)
            x = max(0, (lcd.width - width) // 2)
            Writer.set_textpos(lcd.framebuf, y, x)
            if self._entered and self._mode == "list":
                invert = idx == self._selection
            else:
                invert = label == current_upper
            self.writer_mode.printstring(label, invert=invert)
            if label == current_upper:
                self._draw_active_marker(x, y)
            y += self.font_mode.height() + _ROW_GAP

        selected_label = names[self._selection].upper()[:16] if names else "-"
        if not selected_label:
            selected_label = "-"
        display_selected = selected_label
        if display_selected == "CREATE NEW":
            display_selected = "CREATE"
        if current_upper == "-" and names:
            status_label = "SELECT {}".format(display_selected)
        elif selected_label == current_upper:
            status_label = "ACTIVE {}".format(display_current)
        else:
            status_label = "SELECT {}".format(display_selected)
        if self._entered and self._mode == "list":
            instructions = "UP/DN SELECT  PAGE LONG PICK  SH EXIT"
        else:
            instructions = "PAGE SH ENTER  UP NEXT  DOWN PREV"
        return status_label, instructions

    def _draw_create_editor(self, start_y):
        y = start_y
        values = self._create_values
        for idx, field in enumerate(_CREATE_FIELDS):
            label = self._field_label(field)
            value_text = self._field_value_text(field, values[field])
            text = "{} {}".format(label, value_text)
            invert = self._create_field == idx
            self._draw_text(self.writer_small, self.font_small, text, _PADDING_X, y, invert=invert)
            y += self.font_small.height() + _ROW_GAP
        name = self._compose_pack_name(values)
        self._draw_text(self.writer_small, self.font_small, "NAME {}".format(name[:14]), _PADDING_X, y)

    def _draw_active_marker(self, label_x, label_y):
        mark_text = "<"
        mark_width = self._text_width(self.font_small, mark_text)
        x = label_x - mark_width - 4
        if x < 0:
            x = 0
        y = label_y + self.font_mode.height() - self.font_small.height()
        height = self.font_small.height()
        self.lcd.fill_rect(x, y, mark_width, height, BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        self.writer_small.printstring(mark_text)

    def _draw_status_lines(self, line1, line2):
        lcd = self.lcd
        status_area_height = self.font_small.height() * 2 + _STATUS_GAP + 4
        status_y = lcd.height - status_area_height
        if status_y < self.header_height:
            status_y = self.header_height
        lcd.fill_rect(0, status_y, lcd.width, lcd.height - status_y, BG_COLOR)
        line1_y = status_y + 2
        line2_y = line1_y + self.font_small.height() + _STATUS_GAP
        self._draw_small_centered(line1 or "", line1_y)
        self._draw_small_centered(line2 or "", line2_y)

    def _draw_small_centered(self, text, y):
        if text is None:
            text = ""
        max_width = self.lcd.width - 4
        segment = self._fit_text(self.font_small, text, max_width)
        width = self._text_width(self.font_small, segment)
        x = max(2, (self.lcd.width - width) // 2)
        self.lcd.fill_rect(0, y, self.lcd.width, self.font_small.height(), BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        self.writer_small.printstring(segment)

    def _fit_text(self, font_mod, text, max_width):
        if text is None:
            return ""
        segment = str(text)
        if max_width <= 0:
            return ""

        if self._text_width(font_mod, segment) <= max_width:
            return segment

        original = segment
        suffix = "..."
        while segment and self._text_width(font_mod, segment + suffix) > max_width:
            segment = segment[:-1]

        if not segment:
            return ""

        if segment != original and self._text_width(font_mod, segment + suffix) <= max_width:
            return segment + suffix

        while segment and self._text_width(font_mod, segment) > max_width:
            segment = segment[:-1]

        return segment

    # ---------- Helpers ----------
    def _pack_names(self):
        try:
            names = list(bats.available_packs())
        except Exception:
            names = []
        seen = []
        for name in names:
            if name not in seen:
                seen.append(str(name))
        seen.append("CREATE NEW")
        return seen

    def _current_pack_name(self, state):
        pack = getattr(state, "battery_pack", {}) or {}
        return (state.battery_pack_name or pack.get("key") or "-").upper()[:16]

    def _format_pack_info(self, pack):
        cells = int(pack.get("cells_series", 0) or 0)
        parallel = int(pack.get("parallel", 1) or 1)
        cap_ah = float(pack.get("pack_capacity_Ah", 0.0) or 0.0)
        return f"{cells:02d}s x{parallel} {cap_ah:04.1f}Ah"

    def _draw_text(self, writer, font_mod, text, x, y, invert=False):
        if text is None:
            text = ""
        try:
            x = int(x)
            y = int(y)
        except Exception:
            x = 0
            y = 0

        if x < 0:
            x = 0

        height = font_mod.height()
        max_width = self.lcd.width - x
        if max_width <= 0:
            return

        segment = text
        while segment and self._text_width(font_mod, segment) > max_width:
            segment = segment[:-1]

        self.lcd.fill_rect(x, y, max_width, height, BG_COLOR)
        if not segment:
            return
        Writer.set_textpos(self.lcd.framebuf, y, x)
        writer.printstring(segment, invert=invert)

    @staticmethod
    def _text_width(font_mod, text):
        width = 0
        for ch in text:
            try:
                _, _, adv = font_mod.get_ch(ch)
            except Exception:
                adv = 0
            width += adv
        return width

    def _move_selection(self, state, delta):
        names = self._pack_names()
        if not names:
            return {"handled": True}
        total = len(names)
        self._selection = (self._selection + delta) % total
        self._mark_dirty()
        return {"handled": True, "refresh_self": True}

    def _activate_selection(self, state):
        names = self._pack_names()
        if not names:
            return {"handled": True}
        index = max(0, min(self._selection, len(names) - 1))
        choice = names[index]
        if choice.upper() == "CREATE NEW":
            self._mode = "create"
            self._entered = True
            self._create_field = 0
            current_pack = getattr(state, "battery_pack", {}) or {}
            self._create_values = {
                "cells_series": int(current_pack.get("cells_series", 21) or 21),
                "parallel": int(current_pack.get("parallel", 1) or 1),
                "cell_capacity_mAh": float(
                    current_pack.get("cell_capacity_mAh", current_pack.get("pack_capacity_Ah", 4.5) * 1000.0)
                    or 4500.0
                ),
            }
            self._mark_dirty()
            return {"handled": True, "refresh_self": True}

        try:
            pack = bats.set_current_pack(choice)
        except Exception as exc:
            print("[Batt] select error:", exc)
            return {"handled": True}
        state.set_battery_pack(pack)
        self._entered = False
        self._mode = "list"
        self._sync_selection(state)
        self._mark_dirty()
        self._print_pack_summary(state, pack, action="Selected")
        return {"handled": True, "refresh_all": True}

    def _advance_field(self):
        self._create_field = (self._create_field + 1) % len(_CREATE_FIELDS)

    def _adjust_field(self, direction):
        field = _CREATE_FIELDS[self._create_field]
        step = _FIELD_STEPS[field]
        low, high = _FIELD_LIMITS[field]
        value = self._create_values[field]
        value = value + (direction * step)
        if field != "cell_capacity_mAh":
            value = int(round(value))
        if value < low:
            value = low
        if value > high:
            value = high
        if field == "cell_capacity_mAh":
            value = int(round(value / step)) * step
        self._create_values[field] = value

    def _save_new_pack(self, state):
        values = self._create_values
        cells = int(values["cells_series"])
        parallel = int(values["parallel"])
        capacity = int(round(values["cell_capacity_mAh"]))
        name = self._compose_pack_name(values)
        try:
            bats.save_pack(
                name,
                cells_series=cells,
                parallel=parallel,
                cell_capacity_mAh=capacity,
            )
            pack = bats.set_current_pack(name)
        except Exception as exc:
            print("[Batt] save error:", exc)
            return {"handled": True}
        state.set_battery_pack(pack)
        self._mode = "list"
        self._entered = False
        self._sync_selection(state)
        self._print_pack_summary(state, pack, action="Saved")
        self._mark_dirty()
        return {"handled": True, "refresh_all": True}

    def _compose_pack_name(self, values):
        cells = int(values.get("cells_series", 0) or 0)
        parallel = int(values.get("parallel", 1) or 1)
        capacity = int(round(values.get("cell_capacity_mAh", 0) or 0))
        return f"{cells}sX{parallel}X{capacity}mAh"

    def _field_label(self, field):
        if field == "cells_series":
            return "CELLS"
        if field == "parallel":
            return "PAR"
        if field == "cell_capacity_mAh":
            return "mAh"
        return field.upper()

    def _field_value_text(self, field, value):
        if field == "cells_series":
            return f"{int(value):02d}s"
        if field == "parallel":
            return f"x{int(value):02d}"
        if field == "cell_capacity_mAh":
            return f"{int(value):05d}"
        return str(value)

    def _sync_selection(self, state):
        names = self._pack_names()
        current = (state.battery_pack_name or (getattr(state, "battery_pack", {}) or {}).get("key"))
        if current and current in names:
            self._selection = names.index(current)
        elif names:
            self._selection = 0

    def _mark_dirty(self):
        self._needs_refresh = True
        self._last_snapshot = None

    def _print_pack_summary(self, state, pack, action="Selected"):
        if not isinstance(pack, dict):
            return
        name = str(pack.get("key", "PACK"))
        cells = int(pack.get("cells_series", 0) or 0)
        parallel = int(pack.get("parallel", 1) or 1)
        cap_ah = float(pack.get("pack_capacity_Ah", 0.0) or 0.0)
        cap_wh = float(pack.get("pack_capacity_Wh", 0.0) or 0.0)
        max_current = float(pack.get("max_current_a", 0.0) or 0.0)
        voltage = float(state.battery_voltage())
        soc = bats.compute_soc(pack, voltage)
        remaining_wh = float(getattr(state, "battery_remaining_wh", 0.0) or 0.0)
        if remaining_wh <= 0 and cap_wh > 0:
            remaining_wh = cap_wh * (soc / 100.0)
        print("[Batt] {} pack: {}".format(action, name))
        print(
            "       {:02d}s x{:02d}  {:4.1f}Ah {:5.1f}Wh  max {:4.1f}A".format(
                cells,
                parallel,
                cap_ah,
                cap_wh,
                max_current,
            )
        )
        print("       Now {:5.2f}V  est {:5.1f}Wh remaining".format(voltage, remaining_wh))