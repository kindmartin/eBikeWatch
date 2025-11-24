"""Battery pack metadata, persistence, and helpers."""

try:
    import ujson as json
except ImportError:  # pragma: no cover - CPython fallback
    import json

_CONFIG_FILE = "batts_config.cfg"
_LEGACY_CONFIG_FILE = "currentConfig.cfg"

_DEFAULT_CELL_FULL = 4.15
_DEFAULT_CELL_EMPTY = 3.2
_DEFAULT_CELL_NOMINAL = 3.7
_DEFAULT_CELL_GUARD = 3.3

_DEFAULT_PACK_KEY = "21Sx1x4500mAh"

_BUILTIN_PACKS = {
    "21Sx1x4500mAh": {
        "cells_series": 21,
        "parallel": 1,
        "cell_capacity_mAh": 4500,
        "max_current_a": 30,
    },
    "16Sx2x5000mAh": {
        "cells_series": 16,
        "parallel": 2,
        "cell_capacity_mAh": 5000,
        "max_current_a": 60,
    },
    "40Sx2x3000mAh": {
        "cells_series": 40,
        "parallel": 2,
        "cell_capacity_mAh": 3000,
        "max_current_a": 60,
    },
    "18Sx1x4000mAh": {
        "cells_series": 18,
        "parallel": 1,
        "cell_capacity_mAh": 4000,
        "max_current_a": 60,
    },

}


def _parse_pack_name(name):
    if not isinstance(name, str):
        return {}
    label = name.strip()
    if not label:
        return {}
    compact = label.replace(" ", "")
    if not compact:
        return {}
    lower_compact = compact.lower()
    s_index = lower_compact.find("s")
    if s_index < 0:
        return {}
    prefix = compact[:s_index]
    rest_lower = lower_compact[s_index + 1 :]
    try:
        cells_series = int(prefix or 0)
    except Exception:
        cells_series = 0
    parts_raw = rest_lower.split("x") if rest_lower else []
    parts = [segment.strip() for segment in parts_raw if segment]
    parallel = 1
    capacity_value = 0.0
    capacity_unit = "mAh"
    if parts:
        try:
            parallel = int(parts[0] or 1)
        except Exception:
            parallel = 1
        for segment in parts[1:]:
            seg_lower = segment.lower()
            if seg_lower.endswith("mah"):
                try:
                    capacity_value = float(seg_lower[:-3] or 0)
                    capacity_unit = "mAh"
                except Exception:
                    pass
                break
            if seg_lower.endswith("ah"):
                try:
                    capacity_value = float(seg_lower[:-2] or 0)
                    capacity_unit = "Ah"
                except Exception:
                    pass
                break
    if capacity_unit.lower() == "ah":
        cell_capacity_mAh = capacity_value * 1000.0
    else:
        cell_capacity_mAh = capacity_value
    return {
        "cells_series": int(cells_series),
        "parallel": int(parallel),
        "cell_capacity_mAh": float(cell_capacity_mAh),
    }


def _load_config(config_path=_CONFIG_FILE):
    try:
        with open(config_path, "r") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _legacy_config():
    try:
        with open(_LEGACY_CONFIG_FILE, "r") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_config(cfg, config_path=_CONFIG_FILE):
    try:
        payload = json.dumps(cfg)
        with open(config_path, "w") as fh:
            fh.write(payload)
    except Exception:
        pass


def _normalize_pack(name, params):
    data = {}
    if isinstance(params, dict):
        data.update(params)
    parsed = _parse_pack_name(name)
    for key, value in parsed.items():
        data.setdefault(key, value)

    cells_series = int(data.get("cells_series", data.get("cells", 0)) or 0)
    parallel = int(data.get("parallel", 1) or 1)
    cell_capacity_mAh = float(data.get("cell_capacity_mAh", 0.0) or 0.0)
    max_current_a = float(data.get("max_current_a", 0.0) or 0.0)
    cell_full_v = float(data.get("cell_full_v", _DEFAULT_CELL_FULL) or _DEFAULT_CELL_FULL)
    cell_empty_v = float(data.get("cell_empty_v", _DEFAULT_CELL_EMPTY) or _DEFAULT_CELL_EMPTY)
    cell_nominal_v = float(data.get("cell_nominal_v", _DEFAULT_CELL_NOMINAL) or _DEFAULT_CELL_NOMINAL)
    cell_guard_v = float(data.get("cell_avg_voltage_min", _DEFAULT_CELL_GUARD) or _DEFAULT_CELL_GUARD)
    guard_throttle_v = float(data.get("guard_throttle_v", 1.3) or 1.3)

    if cells_series < 0:
        cells_series = 0
    if parallel < 1:
        parallel = 1
    if cell_capacity_mAh < 0:
        cell_capacity_mAh = 0.0
    if max_current_a < 0:
        max_current_a = 0.0

    pack_capacity_ah = (cell_capacity_mAh / 1000.0) * parallel
    max_voltage = cells_series * cell_full_v
    min_voltage = cells_series * cell_empty_v
    guard_voltage = cells_series * cell_guard_v
    nominal_voltage = cells_series * cell_nominal_v
    pack_capacity_wh = nominal_voltage * pack_capacity_ah
    max_power_w = max_current_a * max_voltage
    cell_voltage_span = cell_full_v - cell_empty_v
    guard_span = cell_full_v - cell_guard_v
    return {
        "key": name,
        "cells_series": cells_series,
        "parallel": parallel,
        "cell_capacity_mAh": cell_capacity_mAh,
        "max_current_a": max_current_a,
        "cell_full_v": cell_full_v,
        "cell_empty_v": cell_empty_v,
        "cell_nominal_v": cell_nominal_v,
        "cell_avg_voltage_min": cell_guard_v,
        "pack_capacity_Ah": pack_capacity_ah,
        "pack_capacity_Wh": pack_capacity_wh,
        "max_voltage": max_voltage,
        "min_voltage": min_voltage,
        "guard_voltage": guard_voltage,
        "nominal_voltage": nominal_voltage,
        "max_power_w": max_power_w,
        "cell_voltage_span": cell_voltage_span,
        "guard_span": guard_span,
        "v_full": max_voltage,
        "v_empty": min_voltage,
        "guard_throttle_v": guard_throttle_v,
    }


def _all_packs(config=None):
    if config is None:
        config = _load_config()

    packs = {}
    for name, params in _BUILTIN_PACKS.items():
        packs[name] = _normalize_pack(name, params)

    cfg_packs = config.get("packs", {}) if isinstance(config, dict) else {}
    for name, params in cfg_packs.items():
        packs[name] = _normalize_pack(name, params)

    if _DEFAULT_PACK_KEY not in packs:
        packs[_DEFAULT_PACK_KEY] = _normalize_pack(_DEFAULT_PACK_KEY, _parse_pack_name(_DEFAULT_PACK_KEY))

    return packs


def available_packs(config_path=_CONFIG_FILE):
    """Return the list of known pack identifiers."""
    config = _load_config(config_path)
    names = sorted(_all_packs(config).keys(), key=lambda item: str(item).lower())
    return names


def pack_info(key=None, config_path=_CONFIG_FILE):
    """Return a dict with voltage and capacity data for the requested pack."""
    config = _load_config(config_path)
    packs = _all_packs(config)
    if key is None:
        key = config.get("current") or _DEFAULT_PACK_KEY
    pack = packs.get(key)
    if pack:
        return pack
    return packs.get(_DEFAULT_PACK_KEY)


def load_current_pack(config_path=_CONFIG_FILE):
    """Read the active pack from config or fall back to the default."""
    config = _load_config(config_path)
    legacy = _legacy_config()
    if not config and legacy:
        selected = legacy.get("battery_pack")
        if selected:
            config = {"current": selected, "packs": {}}
    current_key = config.get("current")
    pack = pack_info(current_key, config_path=config_path)
    return pack


def compute_soc(pack, voltage):
    """Compute linear state-of-charge percentage for a given pack."""
    if pack is None:
        return 0.0
    try:
        v_full = float(pack.get("v_full", 0.0))
        v_empty = float(pack.get("v_empty", 0.0))
        v = float(voltage)
    except Exception:
        return 0.0
    span = v_full - v_empty
    if span <= 0:
        return 0.0
    ratio = (v - v_empty) / span
    if ratio < 0:
        ratio = 0.0
    elif ratio > 1:
        ratio = 1.0
    return ratio * 100.0


def save_pack(name, *, cells_series=None, parallel=None, cell_capacity_mAh=None, max_current_a=None,
              cell_full_v=None, cell_empty_v=None, cell_nominal_v=None, cell_avg_voltage_min=None,
              guard_throttle_v=None, config_path=_CONFIG_FILE):
    """Create or update a pack definition and persist it."""
    config = _load_config(config_path)
    packs = config.setdefault("packs", {})
    existing = packs.get(name, {}).copy()

    if cells_series is not None:
        existing["cells_series"] = int(cells_series)
    if parallel is not None:
        existing["parallel"] = int(parallel)
    if cell_capacity_mAh is not None:
        existing["cell_capacity_mAh"] = float(cell_capacity_mAh)
    if max_current_a is not None:
        existing["max_current_a"] = float(max_current_a)
    if cell_full_v is not None:
        existing["cell_full_v"] = float(cell_full_v)
    if cell_empty_v is not None:
        existing["cell_empty_v"] = float(cell_empty_v)
    if cell_nominal_v is not None:
        existing["cell_nominal_v"] = float(cell_nominal_v)
    if cell_avg_voltage_min is not None:
        existing["cell_avg_voltage_min"] = float(cell_avg_voltage_min)
    if guard_throttle_v is not None:
        existing["guard_throttle_v"] = float(guard_throttle_v)

    if not existing:
        existing.update(_parse_pack_name(name))

    packs[name] = existing
    if not config.get("current"):
        config["current"] = name
    _save_config(config, config_path)
    return pack_info(name, config_path=config_path)


def set_current_pack(name, config_path=_CONFIG_FILE):
    """Select an existing pack as the active one."""
    config = _load_config(config_path)
    packs = _all_packs(config)
    if name not in packs:
        raise ValueError("unknown battery pack: {}".format(name))
    config["current"] = name
    _save_config(config, config_path)
    return pack_info(name, config_path=config_path)


def remove_pack(name, config_path=_CONFIG_FILE):
    """Remove a pack definition from the configuration file."""
    config = _load_config(config_path)
    packs = config.get("packs")
    if isinstance(packs, dict) and name in packs:
        packs.pop(name, None)
        if config.get("current") == name:
            config["current"] = None
        _save_config(config, config_path)


def pack_details(config_path=_CONFIG_FILE):
    """Return a dict mapping pack names to their derived data."""
    packs = _all_packs(_load_config(config_path))
    return packs