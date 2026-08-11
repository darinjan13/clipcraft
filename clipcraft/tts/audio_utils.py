import math

import numpy as np


class DurationMismatch(ValueError):
    pass


def pcm16_bytes(samples) -> bytes:
    audio = np.asarray(samples, dtype=np.float32)
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767).astype('<i2').tobytes()


def pad_pcm16(audio: bytes, *, sample_rate: int, target_duration: float) -> bytes:
    target_bytes = round(float(target_duration) * int(sample_rate)) * 2
    if len(audio) >= target_bytes:
        return audio
    return audio + (b'\x00' * (target_bytes - len(audio)))


def validate_duration(*, actual: float, requested: float, scene_total: float) -> float:
    try:
        actual_value = float(actual)
        requested_value = float(requested)
        scene_value = float(scene_total)
    except (TypeError, ValueError) as exc:
        raise DurationMismatch(
            f'invalid duration values: requested={requested}, scene_total={scene_total}, actual={actual}'
        ) from exc

    values = (actual_value, requested_value, scene_value)
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise DurationMismatch(
            f'invalid duration values: requested={requested}, scene_total={scene_total}, actual={actual}'
        )

    short_tolerance = max(3.0, requested_value * 0.05)
    if (
        actual_value < requested_value - short_tolerance
        or actual_value > requested_value + 2.0
        or actual_value > scene_value + 2.0
    ):
        raise DurationMismatch(
            'narration duration mismatch: '
            f'requested={requested}, scene_total={scene_total}, actual={actual}, '
            f'short_tolerance={short_tolerance}, long_tolerance=2.0'
        )
    return actual_value
