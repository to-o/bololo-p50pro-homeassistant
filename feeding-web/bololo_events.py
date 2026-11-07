"""Read the P50 Pro's variable-length device reports from the App broker."""

import select
import socket
import struct
import time
import uuid


BIT_WIDTHS = (1,) * 11 + (2, 1, 3, 2)
BYTE_WIDTHS = (1,) * 9 + (2,) * 6 + (17, 1)
INTERESTING = {3: "self_cleaning", 4: "quantitative_fit", 7: "detect_status",
               13: "function_status", 22: "bottle_record", 25: "record", 26: "wateryield"}


def unpack_length(read_byte):
    value = 0
    for offset in range(4):
        byte = read_byte()
        value |= (byte & 127) << (offset * 7)
        if byte < 128:
            return value
    raise ValueError("Invalid packet length")


def decode_report(frame):
    if not frame.startswith(b"\0\0\0\3"):
        return {}
    stream = iter(frame[4:])
    try:
        length = unpack_length(lambda: next(stream))
    except StopIteration:
        return {}
    body = bytes(stream)
    # Observed P50 reports carry flag 0, command 0x0093, a 4-byte sequence, action 0x14.
    if len(body) != length or len(body) < 12 or body[:3] != b"\0\0\x93" or body[7] != 0x14:
        return {}
    mask = int.from_bytes(body[8:12], "big")
    flags = [i for i in range(32) if mask & (1 << i)]
    bits = sum(BIT_WIDTHS[i] for i in flags if i < 15)
    offset = 12 + (bits + 7) // 8
    if len(body) != offset + sum(BYTE_WIDTHS[i - 15] for i in flags if i >= 15):
        return {}
    bit_values = int.from_bytes(body[12:offset], "big")
    bit_offset = 0
    data = {}
    for i in flags:
        if i < 15:
            width = BIT_WIDTHS[i]
            value = (bit_values >> bit_offset) & ((1 << width) - 1)
            bit_offset += width
        else:
            width = BYTE_WIDTHS[i - 15]
            value = int.from_bytes(body[offset:offset + width], "big")
            offset += width
        if i in INTERESTING:
            data[INTERESTING[i]] = value
    return data


def read_exact(connection, size):
    result = bytearray()
    while len(result) < size:
        part = connection.recv(size - len(result))
        if not part:
            raise EOFError("MQTT connection closed")
        result.extend(part)
    return bytes(result)


def read_packet(connection):
    header = read_exact(connection, 1)[0]
    size = unpack_length(lambda: read_exact(connection, 1)[0])
    if size > 65536:
        raise ValueError("MQTT packet too large")
    return header, read_exact(connection, size)


def send_packet(connection, header, payload=b""):
    size = len(payload)
    data = bytearray([header])
    while size >= 128:
        data.append((size & 127) | 128)
        size >>= 7
    data.append(size)
    connection.sendall(data + payload)


def field(value):
    encoded = value.encode("utf-8")
    return struct.pack("!H", len(encoded)) + encoded


def reports(host, device_id, app_id, uid, token):
    topic = ("dev2app/" + device_id).encode("ascii")
    with socket.create_connection((host, 1883), timeout=8) as connection:
        client_id = "usr" + uuid.uuid4().hex[:17]
        auth = field("2$" + app_id + "$" + str(uid)) + field(token)
        send_packet(connection, 0x10, b"\x00\x04MQTT\x04\xc2\x00\x2d" + field(client_id) + auth)
        if read_packet(connection) != (0x20, b"\x00\x00"):
            raise OSError("MQTT login rejected")
        send_packet(connection, 0x82, b"\x00\x01" + struct.pack("!H", len(topic)) + topic + b"\x00")
        if read_packet(connection) != (0x90, b"\x00\x01\x00"):
            raise OSError("MQTT subscription rejected")
        yield None
        ping = time.monotonic() + 20
        last_packet = time.monotonic()
        while True:
            if time.monotonic() >= ping:
                send_packet(connection, 0xC0)
                ping = time.monotonic() + 20
            if time.monotonic() - last_packet > 60:
                raise TimeoutError("MQTT broker stopped responding")
            if not select.select([connection], [], [], 1)[0]:
                continue
            header, data = read_packet(connection)
            last_packet = time.monotonic()
            if header >> 4 != 3 or header & 1 or len(data) < 2:
                continue
            size = int.from_bytes(data[:2], "big")
            if data[2:2 + size] == topic:
                offset = 2 + size + (2 if (header >> 1) & 3 else 0)
                parsed = decode_report(data[offset:])
                if parsed:
                    yield parsed
