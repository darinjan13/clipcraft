import unittest

import numpy as np

from audio_utils import DurationMismatch, pad_pcm16, pcm16_bytes, validate_duration


class AudioUtilsTests(unittest.TestCase):
    def test_pcm16_bytes_converts_float_samples_to_two_bytes_each(self):
        samples = np.array([-1.0, -0.5, 0.0, 0.5, 1.0], dtype=np.float32)

        encoded = pcm16_bytes(samples)

        self.assertEqual(len(encoded), 10)
        self.assertEqual(
            np.frombuffer(encoded, dtype='<i2').tolist(),
            [-32767, -16383, 0, 16383, 32767],
        )

    def test_validate_duration_accepts_natural_variation(self):
        validate_duration(actual=87.8, requested=90.0, scene_total=90.0)
        validate_duration(actual=91.5, requested=90.0, scene_total=90.0)

    def test_validate_duration_rejects_excessive_silence_padding(self):
        with self.assertRaises(DurationMismatch):
            validate_duration(actual=82.0, requested=90.0, scene_total=90.0)

    def test_pad_pcm16_adds_silence_to_scene_duration(self):
        one_second = b'\x01\x00' * 10

        padded = pad_pcm16(one_second, sample_rate=10, target_duration=1.5)

        self.assertEqual(len(padded), 30)
        self.assertEqual(padded[:20], one_second)
        self.assertEqual(padded[20:], b'\x00' * 10)

    def test_validate_duration_rejects_audio_that_would_be_cut(self):
        with self.assertRaises(DurationMismatch):
            validate_duration(actual=95.0, requested=90.0, scene_total=90.0)

    def test_validate_duration_rejects_verified_mismatch(self):
        with self.assertRaises(DurationMismatch) as raised:
            validate_duration(actual=258.65, requested=90.0, scene_total=90.0)

        self.assertIn('requested=90.0', str(raised.exception))
        self.assertIn('actual=258.65', str(raised.exception))

    def test_validate_duration_wraps_malformed_values(self):
        with self.assertRaises(DurationMismatch):
            validate_duration(actual='bad', requested=90.0, scene_total=90.0)


if __name__ == '__main__':
    unittest.main()
