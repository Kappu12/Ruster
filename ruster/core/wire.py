"""Small, lossless protobuf wire reader. Unknown fields retain their exact bytes."""
from dataclasses import dataclass
import struct


class FormatError(ValueError):
    pass


def varint(value):
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise FormatError("Integer outside uint64 range")
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data, offset=0):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise FormatError("Truncated variable-length integer")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise FormatError("Variable-length integer exceeds uint64")
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise FormatError("Invalid variable-length integer")


@dataclass(frozen=True)
class Field:
    number: int
    wire: int
    value: object
    raw: bytes


def parse(data):
    result, pos = [], 0
    while pos < len(data):
        start = pos
        tag, pos = read_varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if not 0 < number < 2**29:
            raise FormatError("Invalid protobuf field number")
        if wire == 0:
            value, pos = read_varint(data, pos)
        elif wire in (1, 2, 5):
            if wire == 2:
                length, pos = read_varint(data, pos)
            else:
                length = 8 if wire == 1 else 4
            if length > len(data) - pos:
                raise FormatError("Truncated protobuf field")
            value = data[pos:pos + length]
            pos += length
        else:
            raise FormatError(f"Unsupported protobuf wire type {wire}")
        result.append(Field(number, wire, value, data[start:pos]))
    return result


def encode(number, wire, value):
    tag = varint(number << 3 | wire)
    if wire == 0:
        body = varint(value)
    elif wire == 2:
        body = varint(len(value)) + value
    elif wire in (1, 5):
        if len(value) != (8 if wire == 1 else 4):
            raise FormatError("Wrong fixed field length")
        body = value
    else:
        raise FormatError("Unsupported protobuf field")
    return Field(number, wire, value, tag + body)


def get(fields, number, default=None):
    return next((f.value for f in reversed(fields) if f.number == number), default)


def replace(fields, number, wire, value):
    new = encode(number, wire, value)
    result, done = [], False
    for field in fields:
        if field.number == number:
            if not done:
                result.append(new)
                done = True
        else:
            result.append(field)
    if not done:
        result.append(new)
    return result


def serialize(fields):
    return b"".join(field.raw for field in fields)


def vector(data, default=(0., 0., 0.)):
    fields = parse(data or b"")
    return tuple(struct.unpack('<f', get(fields, i + 1, struct.pack('<f', d)))[0]
                 for i, d in enumerate(default))


def set_vector(data, values):
    fields = parse(data or b"")
    for i, value in enumerate(values, 1):
        fields = replace(fields, i, 5, struct.pack('<f', value))
    return serialize(fields)
