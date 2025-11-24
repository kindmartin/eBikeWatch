"""Reusable horizontal progress line widget for the ST7789 dashboard."""

_BG = 0x0000
_TICK = 0x4208  # dark grey for guide ticks
_NEUTRAL = 0x8410  # mid grey for idle marker


def _split_rgb565(color):
    return (color >> 11) & 0x1F, (color >> 5) & 0x3F, color & 0x1F


def _combine_rgb565(r, g, b):
    return ((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (b & 0x1F)


def _blend_rgb565(color_a, color_b, ratio):
    if ratio <= 0:
        return color_a & 0xFFFF
    if ratio >= 1:
        return color_b & 0xFFFF
    r0, g0, b0 = _split_rgb565(color_a)
    r1, g1, b1 = _split_rgb565(color_b)
    r = int(r0 + (r1 - r0) * ratio + 0.5)
    g = int(g0 + (g1 - g0) * ratio + 0.5)
    b = int(b0 + (b1 - b0) * ratio + 0.5)
    return _combine_rgb565(r, g, b)


class HorizontalSegmentMeter:
    """Draw a 2-pixel tall, multi-color progress line.

    The meter renders an 80px-wide strip split into configurable color
    segments. When the value maps to 0% it shows guide ticks every 8px.
    """

    def __init__(
        self,
        lcd,
        *,
        length=80,
        height=2,
        bg_color=_BG,
        tick_color=_TICK,
        neutral_color=_NEUTRAL,
        segments=None,
        gradient=None,
        color_stops=None,
        direction=1,
    ):
        self.lcd = lcd
        self.length = int(length)
        self.height = int(height)
        self.bg_color = int(bg_color) & 0xFFFF
        self.tick_color = int(tick_color) & 0xFFFF
        self.neutral_color = int(neutral_color) & 0xFFFF
        self.segments = tuple(segments) if segments else ()
        if color_stops:
            self.color_stops = tuple(sorted(color_stops, key=lambda item: item[0]))
        else:
            self.color_stops = ()
        if gradient is not None:
            start, end = gradient
            self.gradient = (int(start) & 0xFFFF, int(end) & 0xFFFF)
        else:
            self.gradient = None
        self.direction = -1 if direction < 0 else 1

    def draw(self, x, y, value, *, min_value, max_value, neutral_range=None):
        """Render the meter at ``(x, y)``.

        ``value`` is clamped between ``min_value`` and ``max_value``. When the
        value is within ``neutral_range`` (tuple of low/high) the meter shows a
        short grey stub. If the value maps to 0% (or cannot be parsed) the
        meter displays guide ticks spaced every 8 pixels.
        """

        lcd = self.lcd
        length = self.length
        height = self.height
        lcd.fill_rect(x, y, length, height, self.bg_color)

        if max_value <= min_value:
            return

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = min_value

        if numeric != numeric:  # NaN guard
            numeric = min_value

        # Neutral idle zone marker.
        if neutral_range:
            low, high = neutral_range
            if numeric >= low and numeric <= high:
                stub = max(3, min(length // 16, length))
                if self.direction > 0:
                    lcd.fill_rect(x, y, stub, height, self.neutral_color)
                else:
                    lcd.fill_rect(x + length - stub, y, stub, height, self.neutral_color)
                return

        span = max_value - min_value
        ratio = (numeric - min_value) / span
        if ratio <= 0:
            self._draw_ticks(x, y)
            return

        if ratio > 1:
            ratio = 1.0

        filled = int(round(ratio * length))
        if filled <= 0:
            self._draw_ticks(x, y)
            return
        if filled > length:
            filled = length

        start_index = 0 if self.direction > 0 else length - filled

        if self.gradient:
            self._draw_gradient(x, y, filled, start_index)
            return

        if self.color_stops:
            self._draw_color_stops(x, y, filled, start_index)
            return

        if not self.segments:
            self._draw_flat(x, y, filled, self.tick_color, start_index)
            return

        self._draw_segments(x, y, filled, start_index)

    def _draw_ticks(self, x, y):
        step = 8
        for offset in range(0, self.length, step):
            self.lcd.fill_rect(x + offset, y, 2, self.height, self.tick_color)

    def _draw_gradient(self, x, y, filled, start_index):
        if not self.gradient:
            return
        start, end = self.gradient
        r0, g0, b0 = _split_rgb565(start)
        r1, g1, b1 = _split_rgb565(end)
        denom = self.length - 1
        if denom <= 0:
            denom = 1
        lcd = self.lcd
        for i in range(filled):
            pos = start_index + i
            base = pos / denom
            if self.direction > 0:
                ratio = base
            else:
                ratio = 1.0 - base
            r = int(r0 + (r1 - r0) * ratio + 0.5)
            g = int(g0 + (g1 - g0) * ratio + 0.5)
            b = int(b0 + (b1 - b0) * ratio + 0.5)
            color = _combine_rgb565(r, g, b)
            lcd.fill_rect(x + pos, y, 1, self.height, color)

    def _draw_flat(self, x, y, filled, color, start_index):
        if filled <= 0:
            return
        self.lcd.fill_rect(x + start_index, y, filled, self.height, color & 0xFFFF)

    def _draw_color_stops(self, x, y, filled, start_index):
        stops = self.color_stops
        if filled <= 0 or len(stops) < 2:
            return
        denom = self.length - 1
        if denom <= 0:
            denom = 1
        lcd = self.lcd
        last_index = len(stops) - 1
        for px in range(filled):
            pos = start_index + px
            base = pos / denom
            if self.direction > 0:
                ratio = base
            else:
                ratio = 1.0 - base
            if ratio <= stops[0][0]:
                color = stops[0][1]
            elif ratio >= stops[last_index][0]:
                color = stops[last_index][1]
            else:
                color = stops[last_index][1]
                for idx in range(last_index):
                    start_pos, start_color = stops[idx]
                    end_pos, end_color = stops[idx + 1]
                    if ratio <= end_pos:
                        span = end_pos - start_pos
                        if span <= 0:
                            color = end_color
                        else:
                            local = (ratio - start_pos) / span
                            if local < 0:
                                local = 0
                            elif local > 1:
                                local = 1
                            color = _blend_rgb565(start_color, end_color, local)
                        break
            lcd.fill_rect(x + pos, y, 1, self.height, color & 0xFFFF)

    def _draw_segments(self, x, y, filled, start_index):
        if filled <= 0 or not self.segments:
            return
        lcd = self.lcd
        segment_start = start_index
        segment_end = start_index + filled
        length = self.length
        for start, end, color in self.segments:
            seg_start = int(start * length)
            seg_end = int(end * length)
            if seg_end <= seg_start:
                continue
            if seg_start >= segment_end or seg_end <= segment_start:
                continue
            draw_start = max(seg_start, segment_start)
            draw_end = min(seg_end, segment_end)
            if draw_end <= draw_start:
                continue
            lcd.fill_rect(x + draw_start, y, draw_end - draw_start, self.height, color & 0xFFFF)
