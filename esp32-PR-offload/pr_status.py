"""
Diagnostic/status tool for PR-offload ESP32
Provides status overview of PR polling, register values, and error states.
Similar to 'status PR' tool on main ESP32.
"""

import uasyncio as asyncio
import time
import json

# Simulated register cache (replace with real shared state)
REG_CACHE = {
    "battery_current": 0.0,
    "motor_input_power": 0.0,
    "vehicle_speed": 0.0,
    "controller_temp": 0.0,
    "motor_temp": 0.0,
    "motor_rpm": 0.0,
    "battery_voltage": 0.0,
    "throttle_voltage": 0.0,
    "brake_voltage_1": 0.0,
    "digital_inputs": 0,
    "warnings": ""
}

ERRORS = []

async def print_status():
    while True:
        print("\n--- PR-offload Status ---")
        for k, v in REG_CACHE.items():
            print(f"{k:18}: {v}")
        if ERRORS:
            print("Errors:", ERRORS)
        else:
            print("No errors.")
        await asyncio.sleep(2)

# For testing: update cache with dummy data
async def update_cache():
    while True:
        for k in REG_CACHE:
            if isinstance(REG_CACHE[k], float):
                REG_CACHE[k] += 0.1
        await asyncio.sleep(1)

async def main():
    asyncio.create_task(update_cache())
    await print_status()


asyncio.run(main())

