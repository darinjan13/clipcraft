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
    """Build zoompan filter for a single scene motion effect."""
    if motion == 'zoom_in':
        return f"zoompan=z='min(zoom+0.01,1.15)':d={nf}:s={w}x{h}:fps=30"
    elif motion == 'zoom_out':
        return (f"zoompan=z='if(eq(on,0),1.15,max(zoom-0.01,1.0))':d={nf}:s={w}x{h}"
                ":fps=30")
    elif motion == 'pan_left':
        s = int(w * 0.1)
        return (f"zoompan=z='1.1':x='min(0,-{s}+on*({s}/{nf}))'"
                f":d={nf}:s={w}x{h}:fps=30")
    elif motion == 'pan_right':
        s = int(w * 0.1)
        return (f"zoompan=z='1.1':x='max(0,{s}-on*({s}/{nf}))'"
                f":d={nf}:s={w}x{h}:fps=30")
    elif motion == 'pan_up':
        s = int(h * 0.1)
        return (f"zoompan=z='1.1':y='min(0,-{s}+on*({s}/{nf}))'"
                f":d={nf}:s={w}x{h}:fps=30")
    elif motion == 'pan_down':
        s = int(h * 0.1)
        return (f"zoompan=z='1.1':y='max(0,{s}-on*({s}/{nf}))'"
                f":d={nf}:s={w}x{h}:fps=30")
    else:
        return f"null"


def render_segment(image_path, motion, duration, output_file, w=1080, h=1920, fps=30):
    """Render one scene image → video segment with motion effect."""
    nf = int(round(duration * fps))
    scale_pad = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                 f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
    mf = motion_filter(motion, nf, w, h)
    cmd = [
        FFMPEG, '-y', '-loop', '1', '-i', image_path,
        '-vf', f"{scale_pad},{mf}",
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


def main():
    if len(sys.argv) != 2:
        print("Usage: render_video.py <job-uuid>", file=sys.stderr)
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
        segments = []
        for i, scene in enumerate(scenes):
            img_path = safe_path(base_dir, scene.get("image", ""))
            if not os.path.isfile(img_path):
                err(f"Scene {i+1} image missing: {img_path}")
                sys.exit(1)

            dur = float(scene.get("duration", 5))
            motion = scene.get("motion", "zoom_in")
            seg_file = os.path.join(temp_dir, f"seg_{i:03d}.mp4")

            log(f"Scene {i+1}: {motion}, {dur}s")
            render_segment(img_path, motion, dur, seg_file, width, height, fps)
            segments.append(seg_file)

        # ---- Step 2: Concatenate all segments ----
        concat_txt = os.path.join(temp_dir, "concat.txt")
        with open(concat_txt, 'w') as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        video_only = os.path.join(temp_dir, "video_only.mp4")
        log("Concatenating segments...")
        run([
            FFMPEG, '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_txt, '-c', 'copy', video_only
        ])

        # ---- Step 3: Add audio + subtitles + final encode ----
        log("Muxing audio and subtitles...")
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