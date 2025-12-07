"""Hardware helper routines for the eBikeWatch runtime."""


def init_dacs_zero(i2c):
    try:
        from drivers.mcp4725 import MCP4725

        d0 = MCP4725(i2c, 0x60)
        d1 = MCP4725(i2c, 0x61)
        d0.write(0)
        d1.write(0)
        print("[DAC] MCP4725 @0x60,0x61 -> 0V")
    except Exception as exc:
        print("[DAC] init error:", exc)


__all__ = ["init_dacs_zero"]
