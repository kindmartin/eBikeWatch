"""Minimal MSP (MultiWii Serial Protocol) helpers shared by both ESP32s."""

HEADER_0 = 0x24  # '$'
HEADER_1 = 0x4D  # 'M'
DIR_TO_DEVICE = 0x3C  # '<'
DIR_FROM_DEVICE = 0x3E  # '>'
MAX_PAYLOAD = 255

# Custom command identifiers (host<->offload)
CMD_PING = 50
CMD_SET_RATE = 51
CMD_POLL_CTRL = 52
CMD_STATUS = 53
CMD_VERSION = 54
CMD_SLEEP_NOW = 55
CMD_WIFI_CONNECT = 56
CMD_REBOOT = 57
CMD_DEBUG = 58
CMD_MAIN_ONLINE = 59
CMD_SNAPSHOT = 60
CMD_TELEMETRY = 200

RESP_OK = 0x00
RESP_ERROR = 0x01
RESP_UNSUPPORTED = 0x02
RESP_BUSY = 0x03


def _checksum(size, cmd, payload):
    checksum = size ^ cmd
    for byte in payload:
        checksum ^= byte
    return checksum & 0xFF


def build_frame(direction, cmd, payload=b""):
    if payload is None:
        payload = b""
    if not isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload)
    size = len(payload)
    if size > MAX_PAYLOAD:
        raise ValueError("payload too large: {} bytes".format(size))
    checksum = _checksum(size, cmd, payload)
    return bytes([HEADER_0, HEADER_1, direction, size, cmd]) + payload + bytes([checksum])


class MSPParser:
    __slots__ = (
        "_state",
        "_index",
        "_direction",
        "_size",
        "_cmd",
        "_payload",
        "errors",
    )

    STATE_WAIT_HEADER0 = 0
    STATE_WAIT_HEADER1 = 1
    STATE_DIR = 2
    STATE_SIZE = 3
    STATE_CMD = 4
    STATE_PAYLOAD = 5
    STATE_CHECKSUM = 6

    def __init__(self):
        self._payload = bytearray()
        self.errors = {"framing": 0, "checksum": 0}
        self.reset()

    def reset(self):
        self._state = self.STATE_WAIT_HEADER0
        self._index = 0
        self._direction = 0
        self._size = 0
        self._cmd = 0
        self._payload = bytearray()

    def feed(self, data):
        if isinstance(data, int):
            data = bytes([data])
        frames = []
        for byte in data:
            self._consume(byte, frames)
        return frames

    def _consume(self, byte, frames):
        if self._state == self.STATE_WAIT_HEADER0:
            if byte == HEADER_0:
                self._state = self.STATE_WAIT_HEADER1
            return
        if self._state == self.STATE_WAIT_HEADER1:
            if byte == HEADER_1:
                self._state = self.STATE_DIR
            else:
                self._state = self.STATE_WAIT_HEADER0
            return
        if self._state == self.STATE_DIR:
            self._direction = byte
            self._state = self.STATE_SIZE
            return
        if self._state == self.STATE_SIZE:
            self._size = byte & 0xFF
            if self._size > MAX_PAYLOAD:
                self.errors["framing"] += 1
                self.reset()
                return
            self._state = self.STATE_CMD
            return
        if self._state == self.STATE_CMD:
            self._cmd = byte & 0xFF
            if self._size == 0:
                self._state = self.STATE_CHECKSUM
            else:
                self._payload = bytearray()
                self._state = self.STATE_PAYLOAD
            return
        if self._state == self.STATE_PAYLOAD:
            self._payload.append(byte)
            if len(self._payload) >= self._size:
                self._state = self.STATE_CHECKSUM
            return
        if self._state == self.STATE_CHECKSUM:
            expected = _checksum(self._size, self._cmd, self._payload)
            if expected == (byte & 0xFF):
                frames.append(
                    {
                        "direction": self._direction,
                        "cmd": self._cmd,
                        "payload": bytes(self._payload),
                    }
                )
            else:
                self.errors["checksum"] += 1
            self.reset()


__all__ = [
    "DIR_TO_DEVICE",
    "DIR_FROM_DEVICE",
    "CMD_PING",
    "CMD_SET_RATE",
    "CMD_POLL_CTRL",
    "CMD_STATUS",
    "CMD_VERSION",
    "CMD_SLEEP_NOW",
    "CMD_WIFI_CONNECT",
    "CMD_REBOOT",
    "CMD_DEBUG",
    "CMD_MAIN_ONLINE",
    "CMD_SNAPSHOT",
    "CMD_TELEMETRY",
    "RESP_OK",
    "RESP_ERROR",
    "RESP_UNSUPPORTED",
    "RESP_BUSY",
    "build_frame",
    "MSPParser",
]
