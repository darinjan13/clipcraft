#!/usr/bin/env python3
"""
Render an AI video from static scene images with motion effects.

Usage: python3 render_video.py <job-uuid>

Produces: /data/jobs/{jobId}/final.mp4 (1080x1920 30fps H.264 AAC)
Also:    /data/jobs/{jobId}/thumbnail.jpg

The manifest is read from /data/jobs/{jobId}/render-manifest.json.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
FFPROBE = shutil.which('ffprobe') or 'ffprobe'


def log(msg):
    print(f"[render] {msg}", flush=True)


def err(msg):
    print(f"[render] ERROR: {msg}", file=sys.stderr, flush=True)


def run(cmd, timeout=600):
    """Run a command, capture output, raise on failure."""
    log(" ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        msg = result.stderr[:3000]
        err(f"Command failed (exit {result.returncode}): {msg}")
        raise RuntimeError(f"FFmpeg error: {msg[:400]}")
    return result


def safe_path(base_dir, rel_path):
    """Prevent path traversal."""
    full = os.path.normpath(os.path.join(base_dir, rel_path))
    if not full.startswith(os.path.normpath(base_dir)):
        raise ValueError(f"Path traversal detected: {rel_path}")
    return full


def motion_filter(motion, nf, w=1080, h=1920):
    """Static scenes: motion effects are disabled.

    Every zoom/pan restarted per segment, which read as a zoom pulse at
    each transition. Scenes now render as still full-bleed frames; scene
    change energy comes from transitions only. The motion argument is
    accepted (manifest compatibility) and ignored.
    """
    return f"null"


def render_clip_segment(clip_path, duration, output_file, w=1080, h=1920, fps=30):
    """Trim a stock clip to scene duration, full-bleed cover, drop clip audio.

    Loops the input so segments extended for transition overlap never run
    dry on short source clips.
    """
    cmd = [
        FFMPEG, '-y', '-stream_loop', '3', '-i', clip_path,
        '-vf', f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-r', str(fps), '-t', str(duration),
        output_file
    ]
    run(cmd)


def xfade_name(transition):
    """Map a manifest transition to an ffmpeg xfade transition (safe default)."""
    mapping = {
        'fade': 'fade',
        'crossfade': 'dissolve',
        'slide_left': 'slideleft',
        'slide_right': 'slideright',
        'blur_dissolve': 'hblur',
    }
    if not isinstance(transition, str):
        return 'dissolve'
    return mapping.get(transition.strip().lower(), 'dissolve')


TRANSITION_OVERLAP = 0.5


def render_segment(image_path, motion, duration, output_file, w=1080, h=1920, fps=30):
    """Render one scene image → video segment with motion effect.

    Full-bleed 9:16: scale up to cover the frame, then center-crop.
    This matches the YouTube Shorts look (no letterbox bars).
    """
    nf = int(round(duration * fps))
    scale_crop = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                  f"crop={w}:{h}")
    mf = motion_filter(motion, nf, w, h)
    cmd = [
        FFMPEG, '-y', '-loop', '1', '-i', image_path,
        '-vf', f"{scale_crop},{mf}",
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-r', str(fps), '-t', str(duration),
        output_file
    ]
    run(cmd)


def generate_thumbnail(video_path, thumb_path, ss=3):
    """Extract a still frame as JPEG thumbnail."""
    try:
        run([
            FFMPEG, '-y', '-i', video_path,
            '-ss', str(ss), '-vframes', '1',
            '-q:v', '2', thumb_path
        ], timeout=30)
    except RuntimeError:
        log("Thumbnail generation failed (non-fatal)")


def resolve_music_track(music_rel):
    """Validate a /data/music track path, return absolute path or None."""
    if not isinstance(music_rel, str) or not music_rel.startswith("/data/music/"):
        return None
    candidate = os.path.normpath(music_rel)
    if not candidate.startswith(os.path.normpath("/data/music")):
        return None
    return candidate if os.path.isfile(candidate) else None


def clamp_volume(value, default=50):
    try:
        volume = int(value)
    except (TypeError, ValueError):
        volume = default
    return max(0, min(100, volume))


def remix_music(job_id, music_rel, volume=50):
    """Re-mix the music bed of an existing final.mp4 without re-encoding video.

    Subtitles are already burned in, so the video stream is copied and only
    the audio track is rebuilt from the manifest narration + bed. Fast.
    """
    if not UUID_RE.match(job_id):
        err(f"Invalid UUID: {job_id}")
        sys.exit(1)
    base_dir = os.path.join("/data/jobs", job_id)
    final_path = os.path.join(base_dir, "final.mp4")
    if not os.path.isfile(final_path):
        err(f"No final video to remix: {final_path}")
        sys.exit(1)
    manifest_path = os.path.join(base_dir, "render-manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    audio_rel = manifest.get("audio", "") or ""
    audio_path = safe_path(base_dir, audio_rel) if audio_rel else ""
    if not audio_path or not os.path.isfile(audio_path):
        # Fall back to whichever narration file exists.
        for candidate in ("narration.wav", "narration_custom.wav"):
            probe = os.path.join(base_dir, candidate)
            if os.path.isfile(probe):
                audio_path = probe
                break
    if not audio_path or not os.path.isfile(audio_path):
        err("No narration audio found for remix")
        sys.exit(1)
    music_path = resolve_music_track(music_rel)
    if not music_path:
        err(f"Music track missing: {music_rel}")
        sys.exit(1)
    volume = clamp_volume(volume)
    if volume <= 0:
        err("Music volume is 0 — nothing to mix")
        sys.exit(1)

    vd = float(run([
        FFPROBE, '-v', 'error', '-show_entries',
        'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
        final_path
    ], timeout=20).stdout.strip())
    ad = float(run([
        FFPROBE, '-v', 'error', '-show_entries',
        'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ], timeout=20).stdout.strip())
    min_dur = min(vd, ad)
    bed_lufs = -36 + volume * 0.2
    fade_d = min(1.0, min_dur / 2)
    out_st = max(min_dur - fade_d, 0)
    tmp_out = os.path.join(base_dir, "final.remix.mp4")
    cmd = [
        FFMPEG, '-y', '-i', final_path, '-i', audio_path,
        '-stream_loop', '-1', '-i', music_path,
        '-filter_complex',
        f"[1:a]loudnorm=I=-16:LRA=11:TP=-1.5,atrim=duration={min_dur}[a-voice];"
        f"[2:a]atrim=duration={min_dur},loudnorm=I={bed_lufs}:LRA=11:TP=-2,"
        f"afade=t=in:st=0:d={fade_d},afade=t=out:st={out_st}:d={fade_d}[a-music];"
        f"[a-voice][a-music]amix=inputs=2:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.95[a]",
        '-map', '0:v:0', '-c:v', 'copy',
        '-map', '[a]', '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart', '-shortest', tmp_out,
    ]
    run(cmd, timeout=300)
    os.replace(tmp_out, final_path)
    manifest["music"] = music_rel
    manifest["musicVolume"] = volume
    if os.path.isfile(manifest_path):
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
    log(f"Remix complete: {os.path.basename(music_path)} at {bed_lufs:.0f} LUFS")


def main():
    if len(sys.argv) == 5 and sys.argv[2] == "--remix-music":
        remix_music(sys.argv[1], sys.argv[3], sys.argv[4])
        sys.exit(0)
    if len(sys.argv) != 2:
        print("Usage: render_video.py <job-uuid> [--remix-music <track> <volume>]", file=sys.stderr)
        sys.exit(1)

    job_id = sys.argv[1]
    if not UUID_RE.match(job_id):
        err(f"Invalid UUID: {job_id}")
        sys.exit(1)

    base_dir = os.path.join("/data/jobs", job_id)
    manifest_path = os.path.join(base_dir, "render-manifest.json")
    if not os.path.isfile(manifest_path):
        err(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    if manifest.get("jobId") != job_id:
        err("jobId mismatch in manifest")
        sys.exit(1)

    width = manifest.get("width", 1080)
    height = manifest.get("height", 1920)
    fps = manifest.get("fps", 30)
    scenes = manifest.get("scenes", [])
    audio_file = manifest.get("audio", "")
    captions_file = manifest.get("captions", "")
    output_file = manifest.get("output", os.path.join(base_dir, "final.mp4"))

    if not scenes:
        err("No scenes in manifest")
        sys.exit(1)

    temp_dir = tempfile.mkdtemp(prefix=f"render_{job_id}_")
    log(f"Temp dir: {temp_dir}")
    try:
        # ---- Step 1: Render each scene as an MP4 segment with motion ----
        # Segments (except the last) are extended by the transition overlap
        # so the xfade chain below lands exactly on the manifest durations.
        overlap = TRANSITION_OVERLAP
        if len(scenes) > 1:
            min_dur = min(float(s.get("duration", 5)) for s in scenes)
            if min_dur < overlap * 2:
                overlap = max(min_dur / 2 - 0.05, 0.1)
                log(f"Short scenes: overlap reduced to {overlap:.2f}s")
        durations = [float(s.get("duration", 5)) for s in scenes]
        segments = []
        for i, scene in enumerate(scenes):
            dur = durations[i]
            render_dur = dur + (overlap if i < len(scenes) - 1 else 0)
            motion = scene.get("motion", "zoom_in")
            seg_file = os.path.join(temp_dir, f"seg_{i:03d}.mp4")

            clip_rel = scene.get("clip") or ""
            if clip_rel:
                clip_path = safe_path(base_dir, clip_rel)
                if not os.path.isfile(clip_path):
                    err(f"Scene {i+1} clip missing: {clip_path}")
                    sys.exit(1)
                log(f"Scene {i+1}: clip, {dur}s")
                render_clip_segment(clip_path, render_dur, seg_file, width, height, fps)
            else:
                img_path = safe_path(base_dir, scene.get("image", ""))
                if not os.path.isfile(img_path):
                    err(f"Scene {i+1} image missing: {img_path}")
                    sys.exit(1)
                log(f"Scene {i+1}: {motion}, {dur}s")
                render_segment(img_path, motion, render_dur, seg_file, width, height, fps)
            segments.append(seg_file)

        # ---- Step 2: Join segments with xfade transitions ----
        # The outgoing scene's transition applies at each boundary; unknown
        # names fall back to dissolve so a render never fails on them.
        video_only = os.path.join(temp_dir, "video_only.mp4")
        if len(segments) == 1:
            log("Single scene: no transitions needed")
            shutil.copyfile(segments[0], video_only)
        else:
            log("Joining segments with xfade transitions...")
            cmd = [FFMPEG, '-y']
            for seg in segments:
                cmd.extend(['-i', seg])
            filters = []
            for i in range(len(segments)):
                filters.append(
                    f"[{i}:v]settb=AVTB,fps={fps},format=yuv420p[v{i}]"
                )
            last_label = "v0"
            running = durations[0]
            for i in range(1, len(segments)):
                trans = xfade_name(scenes[i - 1].get("transition", "crossfade"))
                offset = running
                out_label = f"x{i}"
                filters.append(
                    f"[{last_label}][v{i}]xfade=transition={trans}"
                    f":duration={overlap}:offset={offset}[{out_label}]"
                )
                log(f"Boundary {i}: {trans} at {offset:.2f}s")
                last_label = out_label
                running += durations[i]
            cmd.extend([
                '-filter_complex', ";".join(filters),
                '-map', f'[{last_label}]',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-r', str(fps), video_only
            ])
            run(cmd)

        # ---- Step 3: Add audio (+ optional music bed) + subtitles + final encode ----
        log("Muxing audio and subtitles...")
        music_rel = manifest.get("music", "") or ""
        music_path = None
        if isinstance(music_rel, str) and music_rel.startswith("/data/music/"):
            candidate = os.path.normpath(music_rel)
            if candidate.startswith(os.path.normpath("/data/music")) and os.path.isfile(candidate):
                music_path = candidate
            else:
                log(f"Music track missing, rendering voice-only: {music_rel}")
        mux_cmd = [FFMPEG, '-y', '-i', video_only]

        has_audio = os.path.isfile(safe_path(base_dir, audio_file if audio_file else ""))
        if has_audio:
            audio_path = safe_path(base_dir, audio_file)
            # Get audio duration for clipping
            ad_result = run([
                FFPROBE, '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ], timeout=20)
            ad = float(ad_result.stdout.strip())
            vid_result = run([
                FFPROBE, '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                video_only
            ], timeout=20)
            vd = float(vid_result.stdout.strip())
            log(f"Video duration: {vd:.1f}s, Audio: {ad:.1f}s")

            min_dur = min(vd, ad)
            mux_cmd.extend(['-i', audio_path])
            try:
                music_volume = int(manifest.get('musicVolume', 50))
            except (TypeError, ValueError):
                music_volume = 50
            music_volume = max(0, min(100, music_volume))
            if music_path and music_volume > 0:
                # Music bed normalized so it stays audible regardless of how
                # the track was mastered. Slider 0-100 maps to -36..-16 LUFS
                # (50 lands on the -26 default, 10 under the voice).
                bed_lufs = -36 + music_volume * 0.2
                fade_d = min(1.0, min_dur / 2)
                out_st = max(min_dur - fade_d, 0)
                mux_cmd.extend(['-stream_loop', '-1', '-i', music_path])
                mux_cmd.extend(['-filter_complex',
                    f"[1:a]loudnorm=I=-16:LRA=11:TP=-1.5,atrim=duration={min_dur}[a-voice];"
                    f"[2:a]atrim=duration={min_dur},loudnorm=I={bed_lufs}:LRA=11:TP=-2,"
                    f"afade=t=in:st=0:d={fade_d},afade=t=out:st={out_st}:d={fade_d}[a-music];"
                    f"[a-voice][a-music]amix=inputs=2:duration=first:dropout_transition=0,"
                    f"alimiter=limit=0.95[a]"])
                log(f"Music bed mixed: {os.path.basename(music_path)} at {bed_lufs:.0f} LUFS")
            else:
                mux_cmd.extend(['-filter_complex',
                    f"[1:a]loudnorm=I=-16:LRA=11:TP=-1.5,atrim=duration={min_dur}[a]"])
            mux_cmd.extend(['-map', '0:v:0', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k'])
        else:
            log("No audio file found — video will be silent")
            mux_cmd.extend(['-an'])

        # Subtitles
        has_captions = os.path.isfile(safe_path(base_dir, captions_file if captions_file else ""))
        vf = "copy"
        if has_captions:
            cp = safe_path(base_dir, captions_file)
            vf = f"ass={cp}"

        mux_cmd.extend([
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-profile:v', 'high', '-level', '4.0',
            '-preset', 'medium', '-crf', '23',
            '-vf', vf,
            '-movflags', '+faststart',
            '-shortest', output_file
        ])
        run(mux_cmd)

        # ---- Step 4: Verify output ----
        if not os.path.isfile(output_file):
            err(f"Output not created: {output_file}")
            sys.exit(1)

        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        log(f"Output: {output_file} ({size_mb:.1f} MB)")

        # ---- Step 5: Thumbnail ----
        thumb = os.path.join(base_dir, "thumbnail.jpg")
        generate_thumbnail(output_file, thumb)

        # ---- Step 6: Report ----
        try:
            probe = run([
                FFPROBE, '-v', 'error', '-show_entries',
                'stream=codec_name,codec_type,width,height,duration',
                '-of', 'csv=p=0:nk=1',
                output_file
            ], timeout=30)
            log(f"Probe: {probe.stdout.strip()}")
        except RuntimeError:
            pass

        log("Render complete!")
        sys.exit(0)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()