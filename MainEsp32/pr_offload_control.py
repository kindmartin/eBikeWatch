"""Async helper for commanding the PR-offload MCU from the main ESP32."""

try:
    import ujson as json
except Exception:
    import json

import sys
import time
try:
    import uasyncio as asyncio
except Exception:
    import asyncio

from machine import UART

from HW import (
    PR_UART_ID as MAIN_UART_ID,
    PR_UART_BAUD as MAIN_UART_BAUD,
    PR_UART_TX as MAIN_UART_TX,
    PR_UART_RX as MAIN_UART_RX,
)

_REQ_ID = 1


def _next_req_id():
    global _REQ_ID
    req_id = _REQ_ID
    _REQ_ID = 1 if req_id >= 0x7FFFFFFF else req_id + 1
    return req_id


def _open_uart():
    return UART(
        MAIN_UART_ID,
        baudrate=MAIN_UART_BAUD,
        tx=MAIN_UART_TX,
        rx=MAIN_UART_RX,
        timeout=200,
    )


class AsyncOffloadClient:
    """Async helper that manages UART I/O using uasyncio-friendly polling."""

    def __init__(self, uart=None):
        self._external_uart = uart is not None
        self._uart = uart or _open_uart()
        self._rx_buffer = bytearray()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._uart and not self._external_uart:
            self._uart.deinit()
        self._uart = None

    async def flush(self, duration_ms=0, max_bytes=4096):
        if not self._uart:
            return 0
        deadline = time.ticks_add(time.ticks_ms(), duration_ms)
        dropped = 0
        while self._uart.any() and dropped < max_bytes:
            chunk = self._uart.read()
            if chunk:
                dropped += len(chunk)
            if duration_ms <= 0:
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            await asyncio.sleep_ms(5)
        if dropped:
            self._rx_buffer.clear()
        return dropped

    async def send_command(self, payload, *, wait_ms=1000, verbose=False, flush_before_ms=0):
        if not self._uart:
            raise RuntimeError("UART closed")
        payload = dict(payload)
        payload["req_id"] = _next_req_id()
        target_req_id = payload["req_id"]
        data = json.dumps(payload) + "\n"
        if flush_before_ms:
            await self.flush(flush_before_ms)
        self._uart.write(data)
        deadline = time.ticks_add(time.ticks_ms(), wait_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    self._rx_buffer.extend(chunk)
                    while True:
                        newline = self._rx_buffer.find(b"\n")
                        if newline == -1:
                            break
                        raw = bytes(self._rx_buffer[:newline]).strip()
                        del self._rx_buffer[: newline + 1]
                        if not raw:
                            continue
                        try:
                            decoded = raw.decode("utf-8", "ignore")
                        except Exception:
                            decoded = str(raw)
                        try:
                            frame = json.loads(decoded)
                        except Exception:
                            print("[test] invalid json from offload:", decoded)
                            continue
                        if not isinstance(frame, dict):
                            if verbose:
                                print("[test] ignoring non-dict frame:", frame)
                            continue
                        frame_type = frame.get("type")
                        if frame.get("req_id") == target_req_id:
                            return frame
                        if frame_type in ("telemetry", "event") or frame.get("cmd") == "telemetry":
                            if verbose:
                                print("[test] telemetry/event:", frame)
                            continue
                        if verbose:
                            print("[test] skipping unrelated frame:", frame)
            await asyncio.sleep_ms(10)
        raise RuntimeError("timeout waiting for offload response")

    async def announce_main_online(self, label="main", *, wait_ms=1000):
        payload = {"cmd": "main_online", "label": label, "host_ts": time.ticks_ms()}
        resp = await self.send_command(payload, wait_ms=wait_ms, flush_before_ms=50)
        return resp

    async def reboot(self, *, wait_ms=1000):
        await self.announce_main_online(wait_ms=wait_ms)
        resp = await self.send_command({"cmd": "reboot"}, wait_ms=wait_ms)
        return resp

    async def sleep(self, delay_ms=None, *, wait_ms=1000):
        await self.announce_main_online(wait_ms=wait_ms)
        payload = {"cmd": "sleepNow"}
        if delay_ms is not None:
            payload["delay_ms"] = int(delay_ms)
        resp = await self.send_command(payload, wait_ms=wait_ms)
        return resp

    async def wifi_connect(self, *, wait_ms=5000):
        await self.announce_main_online(wait_ms=wait_ms)
        resp = await self.send_command({"cmd": "wifi_connect"}, wait_ms=wait_ms)
        return resp


def _run_async(coro):
    """Utility to run an async helper when no event loop is active."""
    run = getattr(asyncio, "run", None)
    if run is None:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)
    return run(coro)


async def announce_main_online_async(label="main", *, wait_ms=1000):
    async with AsyncOffloadClient() as client:
        resp = await client.announce_main_online(label=label, wait_ms=wait_ms)
        print("[test] main_online response:", resp)
        return resp


async def reboot_offload_async(*, wait_ms=1000):
    async with AsyncOffloadClient() as client:
        resp = await client.reboot(wait_ms=wait_ms)
        print("[test] reboot response:", resp)
        return resp


async def sleep_offload_async(delay_ms=None, *, wait_ms=1000):
    async with AsyncOffloadClient() as client:
        resp = await client.sleep(delay_ms=delay_ms, wait_ms=wait_ms)
        print("[test] sleep response:", resp)
        return resp


async def wifi_connect_offload_async(*, wait_ms=5000):
    async with AsyncOffloadClient() as client:
        resp = await client.wifi_connect(wait_ms=wait_ms)
        print("[test] wifi_connect response:", resp)
        return resp


def announce_main_online(label="main", *, wait_ms=1000):
    return _run_async(announce_main_online_async(label=label, wait_ms=wait_ms))


def reboot_offload(*, wait_ms=1000):
    return _run_async(reboot_offload_async(wait_ms=wait_ms))


def sleep_offload(delay_ms=None, *, wait_ms=1000):
    return _run_async(sleep_offload_async(delay_ms=delay_ms, wait_ms=wait_ms))


def wifi_connect_offload(*, wait_ms=5000):
    return _run_async(wifi_connect_offload_async(wait_ms=wait_ms))


async def interactive_async():
    async with AsyncOffloadClient() as client:
        resp = await client.announce_main_online()
        print("[test] main_online response:", resp)
        while True:
            sys.stdout.write("cmd> ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()
            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "reboot":
                resp = await client.reboot()
                print("[test] reboot response:", resp)
            elif cmd.startswith("sleep"):
                parts = cmd.split()
                delay = int(parts[1]) if len(parts) > 1 else None
                try:
                    resp = await client.sleep(delay_ms=delay)
                    print("[test] sleep response:", resp)
                except Exception as exc:
                    print("[test] sleep failed:", exc)
            else:
                print("[test] unknown command")


def interactive():
    return _run_async(interactive_async())


if __name__ == "__main__":
    interactive()
