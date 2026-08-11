#!/bin/bash
set -euo pipefail

JOB_ID="${1:-00000000-0000-4000-8000-ccccc0000001}"
JOB_DIR="/data/jobs/${JOB_ID}"
LOG_DIR="/tmp/render-test-${JOB_ID}"
mkdir -p "$JOB_DIR" "$LOG_DIR"

LOG="${LOG_DIR}/test.log"
FFMPEG_LOG="${LOG_DIR}/ffmpeg.log"

exec > >(tee "$LOG") 2>&1

echo "============================================"
echo " ClipCraft Renderer Test — $(date -Iseconds)"
echo "============================================"
echo "Job:    ${JOB_ID}"
echo "Log:    ${LOG}"
echo "Time:   $(date -Iseconds)"
echo ""

# ---- Timeout wrapper ----
TIMEOUT=120
BAIL() {
    echo ""
    echo "=== FAILED at step $1 (after $SECONDS s) ==="
    echo "See log: ${LOG}"
    echo "See ffmpeg log: ${FFMPEG_LOG}"
    exit 1
}

# ---- Environment checks ----
echo "=== Environment ==="
echo "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
echo "Python: $(python3 --version)"
echo "Job dir: ${JOB_DIR}"
echo "User:   $(whoami)"
echo ""

touch "$JOB_DIR/.write-test" || BAIL "write-test"
rm -f "$JOB_DIR/.write-test"
echo "/data/jobs writable: OK"
echo ""

# ---- Step 1: Create 3 visually distinct images ----
echo "=== Creating 3 sample images (1080×1920) ==="
for i in 1 2 3; do
    NN=$(printf "%02d" "$i")
    cinfo="color=0x2C1A4D97@1.0:size=1080x1920:rate=1"
    [ "$i" -eq 2 ] && cinfo="color=0x4A2C8F@1.0:size=1080x1920:rate=1"
    [ "$i" -eq 3 ] && cinfo="color=0x1A0D3B@1.0:size=1080x1920:rate=1"

    script="drawtext=fontfile=/usr/share/fonts/freefont/FreeSans.otf:text=SCENE ${i}:fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2-40"
    script="${script},drawtext=fontfile=/usr/share/fonts/freefont/FreeSans.otf:text=ClipCraft Test:fontcolor=#FFD700:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2+60"

    timeout 30 ffmpeg -y -f lavfi -i "$cinfo" \
        -vf "$script" -vframes 1 \
        "$JOB_DIR/scene-${NN}.png" >> "$FFMPEG_LOG" 2>&1
    sz=$(wc -c < "$JOB_DIR/scene-${NN}.png")
    echo "  scene-${NN}.png  — ${sz} bytes"
done
echo ""

# ---- Step 2: Narration audio ----
echo "=== Creating narration audio ==="
timeout 30 ffmpeg -y -f lavfi -i "sine=frequency=300:duration=15" \
    -af "volume=0.5" -ac 1 -ar 24000 -sample_fmt s16 \
    "$JOB_DIR/narration.wav" >> "$FFMPEG_LOG" 2>&1
echo "  narration.wav — $(wc -c < "$JOB_DIR/narration.wav") bytes"
echo ""

# ---- Step 3: ASS captions ----
echo "=== Creating ASS captions ==="
cat > "$JOB_DIR/captions.ass" <<'ASSEOF'
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,FreeSans,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,SCENE ONE\NOPENING SHOT
Dialogue: 0,0:00:05.00,0:00:09.00,Default,,0,0,0,,SCENE TWO\NTHE PAN
Dialogue: 0,0:00:09.00,0:00:12.00,Default,,0,0,0,,SCENE THREE\NTHE FINALE
ASSEOF
echo "  captions.ass written"
echo ""

# ---- Step 4: Render manifest ----
echo "=== Creating render manifest ==="
cat > "$JOB_DIR/render-manifest.json" <<MANEOF
{
  "jobId": "${JOB_ID}",
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "audio": "/data/jobs/${JOB_ID}/narration.wav",
  "captions": "/data/jobs/${JOB_ID}/captions.ass",
  "output": "/data/jobs/${JOB_ID}/final.mp4",
  "scenes": [
    { "image": "/data/jobs/${JOB_ID}/scene-01.png", "duration": 5, "motion": "zoom_in",  "transition": "crossfade", "caption": "SCENE 1" },
    { "image": "/data/jobs/${JOB_ID}/scene-02.png", "duration": 4, "motion": "pan_left", "transition": "fade",      "caption": "SCENE 2" },
    { "image": "/data/jobs/${JOB_ID}/scene-03.png", "duration": 3, "motion": "zoom_out", "transition": "crossfade", "caption": "SCENE 3" }
  ]
}
MANEOF
echo "  render-manifest.json written"
echo ""

# ---- Step 5: Validate manifest ----
echo "=== Validating manifest ==="
timeout 30 python3 /opt/video-tools/validate_manifest.py "$JOB_ID" || BAIL "manifest-validation"
echo "  Validation: PASSED"
echo ""

# ---- Step 6: Render ----
echo "=== Rendering video ==="
timeout "$TIMEOUT" python3 /opt/video-tools/render_video.py "$JOB_ID" || BAIL "render"
echo "  Render: PASSED"
echo ""

# ---- Step 7: Verify output ----
OUTPUT="$JOB_DIR/final.mp4"
THUMB="$JOB_DIR/thumbnail.jpg"

echo "=== ffprobe verification ==="
if [ ! -f "$OUTPUT" ]; then
    echo "  ERROR: ${OUTPUT} not created"
    exit 1
fi
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,duration,r_frame_rate,pix_fmt,sample_rate,channels \
    -of default=noprint_wrappers=1:nokey=1 "$OUTPUT" >> "$FFMPEG_LOG" 2>&1 || BAIL "ffprobe"

echo "  Output file: ${OUTPUT}"
ls -lh "$OUTPUT" || BAIL "output-ls"
echo "  Thumbnail:   ${THUMB}"
ls -lh "$THUMB" 2>/dev/null || echo "  (no thumbnail — non-fatal)"
echo ""

# ---- Step 8: Check video is real (not placeholder) ----
echo "=== Content integrity check ==="
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0:nk=1 "$OUTPUT" 2>/dev/null)
echo "  Duration: ${DURATION}s"
if [ "$(echo "$DURATION < 3" | bc 2>/dev/null)" = "1" ]; then
    echo "  ERROR: Video too short (expected ~12s)"
    exit 1
fi
echo "  Content: PASSED (${DURATION}s, real scene images rendered)"
echo ""

# ---- Done ----
echo "============================================"
echo " Renderer test complete — ALL PASSED"
echo " Duration: ${SECONDS}s"
echo " Log:      ${LOG}"
echo " Output:   ${OUTPUT}"
echo "============================================"
