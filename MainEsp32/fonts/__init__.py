# Font package bootstrap for ST7789 UI

_FONT_ALIASES = {
    "font00_24": "Font00_24",
    "Font00_24": "Font00_24",
    "seven_segment_20": "sevenSegment_20",
    "seven_segment_30": "sevenSegment_30",
    "seven_segment_24": "sevenSegment_24",
    "seven_segment_40": "sevenSegment_40",
    "seven_segment_80": "sevenSegment_80",
    "seven-segment_20": "sevenSegment_20",
    "seven-segment_30": "sevenSegment_30",
    "seven-segment_24": "sevenSegment_24",
    "seven-segment_40": "sevenSegment_40",
    "seven-segment_80": "sevenSegment_80",
    "sevenSegment_20": "sevenSegment_20",
    "sevenSegment_30": "sevenSegment_30",
    "sevenSegment_24": "sevenSegment_24",
    "sevenSegment_40": "sevenSegment_40",
    "sevenSegment_80": "sevenSegment_80",
}


def load(name):
    module_name = _FONT_ALIASES.get(name, name)
    if module_name in globals():
        return globals()[module_name]
    mod = __import__("fonts." + module_name, None, None, (module_name,))
    globals()[module_name] = mod
    return mod
