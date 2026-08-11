"""ClipCraft local TTS server — Kokoro preferred, Piper fallback.

No cloud TTS (no gTTS, no ElevenLabs).
If both Kokoro and Piper fail, returns 500.

POST /tts  { "text": "...", "voice": "af_heart", "language": "en" }
GET  /health

Voice selection:
- Friendly labels (e.g. "Warm narrator", "Studio neutral", "Energetic guide")
  map to real Kokoro voices.
- Raw Kokoro voice codes (e.g. "af_heart", "am_michael", "af_nova") pass through.
- Any other/empty voice falls back to Piper when available.
"""

import io
import os
import wave

from flask import Flask, jsonify, request, send_file

from audio_utils import DurationMismatch, pad_pcm16, pcm16_bytes, validate_duration

app = Flask(__name__)

kokoro_ok = False
piper_ok = False
_kokoro_pipeline = None
_piper_voice = None
_piper_model_path = os.environ.get(
    'PIPER_MODEL',
    '/app/models/en_US-lessac-medium.onnx'
)

# Generate-page voice options -> real Kokoro voices.
# 'af_' = American English female, 'am_' = American English male.
KOKORO_VOICE_BY_LABEL = {
    "warm narrator": "af_heart",
    "studio neutral": "am_michael",
    "energetic guide": "af_nova",
}

# American English Kokoro voices this image can synthesize.
_KOKORO_AMERICAN_VOICES = {
    "af_heart", "af_bella", "af_nicole", "af_jojo", "af_sky", "af_alloy",
    "af_rebecca", "af_sarah", "af_nova", "af_jessica", "af_river",
    "am_michael", "am_fenrir", "am_puck", "am_liam", "am_onyx", "am_echo",
}


def _resolve_voice(voice):
    """Resolve a friendly label or pass through a known Kokoro voice code.

    Returns a Kokoro voice code, or None when the request should fall back
    to Piper.
    """
    if not voice:
        return None
    value = str(voice).strip()
    label = KOKORO_VOICE_BY_LABEL.get(value.lower())
    if label:
        return label
    return value if value in _KOKORO_AMERICAN_VOICES else None

# --- Kokoro ---
# NOTE: lazy-initialized at first use (not import time). gunicorn runs with
# --preload, so building the torch/tokenizer-backed pipeline in the master
# process and then forking deadlocks the worker on first inference.
try:
    import kokoro  # noqa: F401  (verify package is installed)
except Exception as e:
    print(f"[kokoro] import failed: {e}", flush=True)


def _get_kokoro_pipeline():
    global _kokoro_pipeline, kokoro_ok
    if _kokoro_pipeline is None:
        from kokoro import KPipeline
        _kokoro_pipeline = KPipeline(lang_code='a')
        kokoro_ok = True
    return _kokoro_pipeline

# --- Piper ---
try:
    import piper
    _piper_voice = piper.PiperVoice.load(_piper_model_path)
    piper_ok = True
except Exception as e:
    print(f"[piper] init failed: {e}", flush=True)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'kokoro': kokoro_ok,
        'piper': piper_ok,
    })


@app.route('/tts', methods=['POST'])
def synthesize():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    voice = data.get('voice', 'af_heart')
    language = data.get('language', 'en')
    kokoro_voice = _resolve_voice(voice)
    requested_duration = data.get('requested_duration')
    scene_duration = data.get('scene_duration')

    if not text:
        return jsonify({'error': 'text is required'}), 400
    if len(text) > 10000:
        return jsonify({'error': 'text too long (max 10000 chars)'}), 400

    try:
        if kokoro_voice:
            try:
                return _kokoro(text, kokoro_voice, requested_duration, scene_duration)
            except DurationMismatch:
                raise
            except Exception as e:
                # Kokoro init/inference failed at request time — fall back to
                # Piper so real jobs still get audio.
                print(f"[kokoro] request failed; falling back to piper: {e}", flush=True)
        if piper_ok:
            return _piper(text, requested_duration, scene_duration)
        if kokoro_ok:
            return _kokoro(
                text,
                kokoro_voice or 'af_heart',
                requested_duration,
                scene_duration,
            )
        return jsonify({
            'error': 'No TTS backend available. Both Kokoro and Piper failed to initialize.'
        }), 500
    except DurationMismatch as e:
        return jsonify({
            'error': 'TTS_DURATION_MISMATCH',
            'message': str(e),
            'requested_duration': requested_duration,
            'scene_duration': scene_duration,
        }), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _kokoro(text, voice, requested_duration=None, scene_duration=None):
    samplerate = 24000
    chunks = []
    pipeline = _get_kokoro_pipeline()

    for gs, ps, audio in pipeline(text, voice=voice, speed=1.0):
        chunks.append(pcm16_bytes(audio.numpy()))

    raw = b''.join(chunks)
    spoken_dur = len(raw) / (samplerate * 2)
    _validate_requested_duration(spoken_dur, requested_duration, scene_duration)
    if scene_duration is not None:
        raw = pad_pcm16(raw, sample_rate=samplerate, target_duration=float(scene_duration))
    dur = len(raw) / (samplerate * 2)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(raw)
    buf.seek(0)

    resp = send_file(buf, mimetype='audio/wav', as_attachment=True,
                     download_name='narration.wav')
    resp.headers['X-Duration-Seconds'] = str(round(dur, 2))
    resp.headers['X-Spoken-Duration-Seconds'] = str(round(spoken_dur, 2))
    resp.headers['X-Requested-Duration'] = str(requested_duration or '')
    resp.headers['X-Scene-Duration'] = str(scene_duration or '')
    return resp


def _piper(text, requested_duration=None, scene_duration=None):
    chunks = list(_piper_voice.synthesize(text))
    if not chunks:
        raise ValueError('Piper returned no audio')

    result = b''.join(
        (chunk.audio_float_array * 32767).astype('int16').tobytes()
        for chunk in chunks
    )
    samplerate = _piper_voice.config.sample_rate
    audio_data = result
    spoken_dur = len(audio_data) / (samplerate * 2)
    _validate_requested_duration(spoken_dur, requested_duration, scene_duration)
    if scene_duration is not None:
        audio_data = pad_pcm16(
            audio_data,
            sample_rate=samplerate,
            target_duration=float(scene_duration),
        )
    dur = len(audio_data) / (samplerate * 2)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_data)
    buf.seek(0)

    resp = send_file(buf, mimetype='audio/wav', as_attachment=True,
                     download_name='narration.wav')
    resp.headers['X-Duration-Seconds'] = str(round(dur, 2))
    resp.headers['X-Spoken-Duration-Seconds'] = str(round(spoken_dur, 2))
    resp.headers['X-Requested-Duration'] = str(requested_duration or '')
    resp.headers['X-Scene-Duration'] = str(scene_duration or '')
    return resp


def _validate_requested_duration(actual, requested, scene_total):
    if requested is None or scene_total is None:
        return
    validate_duration(
        actual=actual,
        requested=requested,
        scene_total=scene_total,
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"TTS server starting on :{port} (kokoro={kokoro_ok}, piper={piper_ok})", flush=True)
    app.run(host='0.0.0.0', port=port, debug=False)
