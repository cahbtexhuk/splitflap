import zlib

from cobs import cobs


def encode_frame(payload):
    checksum = zlib.crc32(payload) & 0xFFFFFFFF
    return cobs.encode(payload + checksum.to_bytes(4, 'little')) + b'\0'


def decode_frame(frame):
    try:
        decoded = cobs.decode(frame)
    except cobs.DecodeError as error:
        raise ValueError('Invalid COBS frame') from error
    if len(decoded) < 4:
        raise ValueError('Frame is too short')
    payload, checksum = decoded[:-4], decoded[-4:]
    if zlib.crc32(payload) & 0xFFFFFFFF != int.from_bytes(checksum, 'little'):
        raise ValueError('Invalid CRC')
    return payload