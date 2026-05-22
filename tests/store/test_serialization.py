import unittest

from brain_ds.store.errors import CorruptVectorError
from brain_ds.store.serialization import (
    decode_json,
    decode_vector,
    encode_json,
    encode_vector,
)


class TestSerialization(unittest.TestCase):
    def test_encode_json_is_sort_stable(self):
        payload = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}

        encoded = encode_json(payload)

        self.assertEqual(encoded, '{"a":1,"b":2,"nested":{"y":25,"z":26}}')

    def test_decode_json_none_and_empty_passthrough(self):
        self.assertIsNone(decode_json(None))
        self.assertIsNone(decode_json(""))

    def test_vector_roundtrip_float32(self):
        vector = [1.5, -2.25, 0.0]

        encoded = encode_vector(vector)
        decoded = decode_vector(encoded, dimensions=3)

        self.assertEqual(len(encoded), 12)
        self.assertEqual(decoded, [1.5, -2.25, 0.0])

    def test_decode_vector_raises_on_wrong_length(self):
        encoded = encode_vector([1.0, 2.0])

        with self.assertRaises(CorruptVectorError):
            decode_vector(encoded, dimensions=3)


if __name__ == "__main__":
    unittest.main()
