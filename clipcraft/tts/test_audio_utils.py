import unittest

import numpy as np

from audio_utils import DurationMismatch, adaptive_speed, cap_silence, pad_pcm16, pcm16_bytes, validate_duration


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

    def test_adaptive_speed_targets_requested_duration(self):
        self.assertAlmostEqual(adaptive_speed(actual=34.8, requested=30.0), 1.16, places=2)
        self.assertAlmostEqual(adaptive_speed(actual=25.725, requested=30.0), 0.86, places=2)

    def _tone_with_pause(self, tone_len=2400, pause_len=24000, rate=24000):
        # Cosine starts at peak amplitude so tone edges are never silent.
        tone = (np.cos(2 * np.pi * 440 * np.arange(tone_len) / rate) * 10000).astype('<i2')
        pause = np.zeros(pause_len, dtype='<i2')
        return (tone.tobytes() + pause.tobytes() + tone.tobytes()), rate

    def test_cap_silence_shortens_long_pauses(self):
        audio, rate = self._tone_with_pause()
        capped = cap_silence(audio, sample_rate=rate, max_pause_seconds=0.4)

        # 1.0s pause -> 0.4s; tones untouched: 0.1 + 0.4 + 0.1 = 0.6s
        self.assertEqual(len(capped), int(0.6 * rate) * 2)

    def test_cap_silence_keeps_short_pauses(self):
        audio, rate = self._tone_with_pause(pause_len=4800)
        capped = cap_silence(audio, sample_rate=rate, max_pause_seconds=0.4)

        self.assertEqual(capped, audio)

    def test_cap_silence_trims_edges(self):
        silence = np.zeros(24000, dtype='<i2').tobytes()
        tone = (np.cos(2 * np.pi * 440 * np.arange(2400) / 24000) * 10000).astype('<i2').tobytes()
        capped = cap_silence(silence + tone + silence, sample_rate=24000, edge_seconds=0.2)

        # 1.0s edges -> 0.2s each: 0.2 + 0.1 + 0.2 = 0.5s
        self.assertEqual(len(capped), int(0.5 * 24000) * 2)


if __name__ == '__main__':
    unittest.main()
