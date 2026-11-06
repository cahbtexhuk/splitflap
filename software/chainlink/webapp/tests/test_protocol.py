import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol import decode_frame, encode_frame


class ProtocolTests(unittest.TestCase):
    def test_round_trip_with_zero_bytes(self):
        payload = b'\x08\x01\x22\x00'
        frame = encode_frame(payload)
        self.assertEqual(frame[-1:], b'\0')
        self.assertNotIn(b'\0', frame[:-1])
        self.assertEqual(decode_frame(frame[:-1]), payload)

    def test_corrupted_frame_is_rejected(self):
        frame = bytearray(encode_frame(b'hello')[:-1])
        frame[2] ^= 1
        with self.assertRaises(ValueError):
            decode_frame(frame)


if __name__ == '__main__':
    unittest.main()