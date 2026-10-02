import math

import numpy as np


class DurationMismatch(ValueError):
    pass


def adaptive_speed(*, actual: float, requested: float) -> float:
    return max(0.5, min(2.0, float(actual) / float(requested)))


def pcm16_bytes(samples) -> bytes:
    audio = np.asarray(samples, dtype=np.float32)
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767).astype('<i2').tobytes()


def pad_pcm16(audio: bytes, *, sample_rate: int, target_duration: float) -> bytes:
    target_bytes = round(float(target_duration) * int(sample_rate)) * 2
    if len(audio) >= target_bytes:
        return audio
    return audio + (b'\x00' * (target_bytes - len(audio)))


def cap_silence(
    audio: bytes,
    *,
    sample_rate: int,
    threshold: int = 500,
    max_pause_seconds: float = 0.4,
    edge_seconds: float = 0.2,
) -> bytes:
    """Shorten over-long pauses in mono int16 PCM.

    TTS engines leave generous inter-sentence gaps (measured: 19% of a
    105s narration was silence, longest pause 1.4s). Runs of near-silent
    samples longer than max_pause_seconds are truncated to it; leading
    and trailing silence is trimmed to edge_seconds. Speech is untouched.
    """
    samples = np.frombuffer(audio, dtype='<i2').copy()
    if samples.size == 0:
        return audio
    rate = int(sample_rate)
    if rate <= 0:
        return audio
    silent = np.abs(samples) < threshold
    if bool((~silent).all()):
        return audio
    max_pause = max(int(round(max_pause_seconds * rate)), 1)
    edge = max(int(round(edge_seconds * rate)), 0)
    # Boundaries (start, end) of each silent run, in samples.
    padded = np.concatenate(([False], silent, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    runs = list(zip(changes[::2], changes[1::2]))
    parts = []
    cursor = 0
    last = len(runs) - 1
    for index, (start, end) in enumerate(runs):
        is_leading = index == 0 and start == 0
        is_trailing = index == last and end == samples.size
        if is_leading:
            keep_from, keep_to = max(end - edge, 0), end
        elif is_trailing:
            keep_from, keep_to = start, start + edge
        else:
            keep_from, keep_to = start, min(end, start + max_pause)
        parts.append(samples[cursor:start])
        parts.append(samples[keep_from:keep_to])
        cursor = end
    parts.append(samples[cursor:])
    return b''.join(part.tobytes() for part in parts)
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
