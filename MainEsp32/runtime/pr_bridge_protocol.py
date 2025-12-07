"""Shared constants and helpers for the Phaserunner binary bridge protocol."""

try:
    import ustruct as struct  # type: ignore
except ImportError:  # pragma: no cover
    import struct  # type: ignore

START_BYTE = 0xAA
END_BYTE = 0x55
PROTOCOL_VERSION = 0x01
MAX_PAYLOAD = 240  # keep plenty of headroom under 255

FRAME_TYPE_TELEMETRY = 0x01
FRAME_TYPE_COMMAND = 0x02
FRAME_TYPE_RESPONSE = 0x81
FRAME_TYPE_EVENT = 0xF0

CMD_PING = 0x01
CMD_SET_RATE = 0x02
CMD_SET_FIELDS = 0x03
CMD_SLEEP = 0x04
CMD_MAIN_ONLINE = 0x05
CMD_WIFI_CONNECT = 0x06
CMD_STATUS = 0x07
CMD_VERSION = 0x08
CMD_REBOOT = 0x09
CMD_DEBUG = 0x0A
CMD_POLL_CTRL = 0x0B
CMD_SNAPSHOT = 0x0C

STATUS_OK = 0x00
STATUS_ERROR = 0x01
STATUS_UNSUPPORTED = 0x02
STATUS_BUSY = 0x03

FAST_FIELDS = (
    "battery_current",
    "vehicle_speed",
    "motor_input_power",
)

SLOW_FIELDS = (
    "controller_temp",
    "motor_temp",
    "motor_rpm",
    "battery_voltage",
    "throttle_voltage",
    "brake_voltage_1",
    "digital_inputs",
    "warnings",
)

FAST_DEFAULT_MASK = (1 << len(FAST_FIELDS)) - 1
SLOW_DEFAULT_MASK = (1 << len(SLOW_FIELDS)) - 1

_COMMAND_NAME_TO_ID = {
    "ping": CMD_PING,
    "set_rate": CMD_SET_RATE,
    "set_fields": CMD_SET_FIELDS,
    "set_fast": CMD_SET_RATE,
    "set_slow": CMD_SET_RATE,
    "sleep": CMD_SLEEP,
    "main_online": CMD_MAIN_ONLINE,
    "wifi_connect": CMD_WIFI_CONNECT,
    "status": CMD_STATUS,
    "version": CMD_VERSION,
    "reboot": CMD_REBOOT,
    "debug": CMD_DEBUG,
    "poll": CMD_POLL_CTRL,
    "snapshot": CMD_SNAPSHOT,
}

COMMAND_ID_TO_NAME = {value: key for key, value in _COMMAND_NAME_TO_ID.items()}


def command_id_from_name(name):
    return _COMMAND_NAME_TO_ID.get(str(name or "").lower())


def crc8_maxim(data):
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame(frame_type, seq, payload):
    if payload is None:
        payload = b""
    if not isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload)
    length = len(payload)
    if length > MAX_PAYLOAD:
        raise ValueError("payload too large: {} bytes".format(length))
    header = bytearray(
        [START_BYTE, PROTOCOL_VERSION & 0xFF, frame_type & 0xFF, seq & 0xFF, length & 0xFF]
    )
    crc_input = header[1:] + payload
    checksum = crc8_maxim(crc_input)
    header.extend(payload)
    header.append(checksum)
    header.append(END_BYTE)
    return bytes(header)


class FrameParser:
    __slots__ = (
        "_state",
        "_header_index",
        "_version",
        "_frame_type",
        "_seq",
        "_length",
        "_payload",
        "errors",
    )

    STATE_WAIT = 0
    STATE_HEADER = 1
    STATE_PAYLOAD = 2
    STATE_CHECKSUM = 3
    STATE_END = 4

    def __init__(self):
        self._payload = bytearray()
        self.errors = {
            "crc": 0,
            "length": 0,
            "framing": 0,
        }
        self.reset()

    def reset(self):
        self._state = self.STATE_WAIT
        self._header_index = 0
        self._version = 0
        self._frame_type = 0
        self._seq = 0
        self._length = 0
        self._payload.clear()

    def feed(self, data):
        if isinstance(data, int):
            data = bytes([data])
        frames = []
        for byte in data:
            self._consume(byte, frames)
        return frames

    def _consume(self, byte, frames):
        if self._state == self.STATE_WAIT:
            if byte == START_BYTE:
                self._state = self.STATE_HEADER
                self._header_index = 0
                self._payload.clear()
            return
        if self._state == self.STATE_HEADER:
            if self._header_index == 0:
                self._version = byte
                if self._version != PROTOCOL_VERSION:
                    self.reset()
                    return
            elif self._header_index == 1:
                self._frame_type = byte
            elif self._header_index == 2:
                self._seq = byte
            elif self._header_index == 3:
                self._length = byte
                if self._length > MAX_PAYLOAD:
                    self.errors["length"] += 1
                    self.reset()
                    return
                if self._length == 0:
                    self._state = self.STATE_CHECKSUM
                else:
                    self._state = self.STATE_PAYLOAD
                self._header_index += 1
                return
            self._header_index += 1
            return
        if self._state == self.STATE_PAYLOAD:
            self._payload.append(byte)
            if len(self._payload) >= self._length:
                self._state = self.STATE_CHECKSUM
            return
        if self._state == self.STATE_CHECKSUM:
            crc_input = bytearray(
                [self._version & 0xFF, self._frame_type & 0xFF, self._seq & 0xFF, self._length & 0xFF]
            )
            crc_input.extend(self._payload)
            expected = crc8_maxim(crc_input)
            if expected != (byte & 0xFF):
                self.errors["crc"] += 1
                self.reset()
                return
            self._state = self.STATE_END
            return
        if self._state == self.STATE_END:
            if byte == END_BYTE:
                frames.append(
                    {
                        "version": self._version,
                        "type": self._frame_type,
                        "seq": self._seq,
                        "payload": bytes(self._payload),
                    }
                )
            else:
                self.errors["framing"] += 1
            self.reset()


def pack_float(value):
    if value is None:
        value = float("nan")
    try:
        value = float(value)
    except Exception:
        value = float("nan")
    return struct.pack("<f", value)


def unpack_float(data, offset):
    return struct.unpack_from("<f", data, offset)[0]


def encode_field_block(fields, mask, values):
    buf = bytearray()
    for idx, name in enumerate(fields):
        if mask & (1 << idx):
            buf.extend(pack_float(values.get(name)))
    return buf


def decode_field_block(fields, mask, data, offset=0):
    result = {}
    for idx, name in enumerate(fields):
        if mask & (1 << idx):
            result[name] = unpack_float(data, offset)
            offset += 4
    return result, offset
