"""Boot/status display helpers extracted from t.py."""

import fonts
from UI_helpers.writer import Writer


def _font_text_width(font_mod, text):
    width = 0
    for ch in text:
        try:
            _, _, advance = font_mod.get_ch(ch)
        except Exception:
            advance = 0
        width += advance
    return width


def show_boot_message(ui_display, lines=None):
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


def compose_status_lines(state, header):
    lines = [header or "Status"]
    if state is None:
        lines.extend(
            [
                "Trip --.- km @ --.- km/h",
                "Used --.- Wh",
                "Left --.- Wh",
                "Battery ---%",
            ]
        )
        return lines

    def _safe_float(value, default=0.0, min_value=None, max_value=None):
        try:
            result = float(value)
        except Exception:
            result = default
        if min_value is not None and result < min_value:
            result = min_value
        if max_value is not None and result > max_value:
            result = max_value
        return result

    trip_km = _safe_float(getattr(state, "trip_distance_km", 0.0), 0.0, 0.0)
    trip_speed = _safe_float(getattr(state, "trip_speed_kmh", 0.0), 0.0, 0.0)
    used_wh = _safe_float(getattr(state, "wh_total", 0.0), 0.0, 0.0)
    remain_wh = _safe_float(getattr(state, "battery_remaining_wh", 0.0), 0.0, 0.0)
    max_wh = _safe_float(getattr(state, "battery_max_wh", 0.0), 0.0, 0.0)
    if max_wh <= 0:
        approx_capacity = used_wh + remain_wh
        if approx_capacity > 0:
            max_wh = approx_capacity
    batt_pct = 0.0
    if max_wh > 0:
        batt_pct = (remain_wh / max_wh) * 100.0
    batt_pct = _safe_float(batt_pct, 0.0, 0.0, 100.0)

    lines.append("Trip {:>5.2f} km @ {:>4.1f} km/h".format(trip_km, trip_speed))
    lines.append("Used {:>6.1f} Wh".format(used_wh))
    lines.append("Left {:>6.1f} Wh".format(remain_wh))
    lines.append("Battery {:>5.1f}%".format(batt_pct))
    return lines


def show_status_screen(ui_display, header, state):
    if ui_display is None:
        return
    try:
        lines = compose_status_lines(state, header)
    except Exception:
        lines = [header or "Status"]
    show_boot_message(ui_display, lines)
