#!/usr/bin/env python3
"""Validate a render manifest for the AI Video Factory. Exit 0 if valid, 1 if not."""

import json
import os
import re
import sys

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
ALLOWED_MOTIONS = {'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'}
ALLOWED_TRANSITIONS = {'fade', 'crossfade', 'slide_left', 'slide_right'}

def validate_uuid(v):
    if not UUID_RE.match(str(v)):
        raise ValueError(f"Invalid UUID: {v}")

def safe_path(base, rel):
    full = os.path.normpath(os.path.join(base, rel))
    if not full.startswith(os.path.normpath(base)):
        raise ValueError(f"Path traversal: {rel}")
    return full

def main():
    if len(sys.argv) != 2:
        print("Usage: validate_manifest.py <job-uuid>", file=sys.stderr)
        sys.exit(1)

    job_id = sys.argv[1]
    try:
        validate_uuid(job_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    base = os.path.join("/data/jobs", job_id)
    manifest_file = os.path.join(base, "render-manifest.json")
    if not os.path.isfile(manifest_file):
        print(f"ERROR: manifest not found at {manifest_file}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_file, 'r') as f:
        m = json.load(f)

    errors = []
    if m.get("jobId") != job_id:
        errors.append("jobId mismatch")

    if m.get("width", 1080) < 200 or m.get("height", 1920) < 200:
        errors.append("invalid dimensions")

    audio = m.get("audio", "")
    if audio:
        ap = safe_path(base, audio)
        if not os.path.isfile(ap):
            errors.append(f"audio not found: {ap}")

    captions = m.get("captions", "")
    if captions:
        cp = safe_path(base, captions)
        if not os.path.isfile(cp):
            print(f"NOTE: captions file not found: {cp} (may be optional)")

    scenes = m.get("scenes", [])
    if not scenes:
        errors.append("no scenes")
    else:
        total_dur = 0
        for i, s in enumerate(scenes):
            idx = i + 1
            img = s.get("image", "")
            dur = s.get("duration", 0)
            motion = s.get("motion", "zoom_in")
            transition = s.get("transition", "crossfade")

            if img:
                ip = safe_path(base, img)
                if not os.path.isfile(ip):
                    errors.append(f"scene {idx} image not found: {ip}")
            else:
                errors.append(f"scene {idx} missing image path")

            if not isinstance(dur, (int, float)) or dur < 1:
                errors.append(f"scene {idx} invalid duration: {dur}")
            total_dur += dur

            if motion not in ALLOWED_MOTIONS:
                errors.append(f"scene {idx} invalid motion: '{motion}'")
            if transition not in ALLOWED_TRANSITIONS:
                errors.append(f"scene {idx} invalid transition: '{transition}'")

    if errors:
        print("Validation FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Manifest valid ({len(scenes)} scenes, {total_dur:.1f}s total)")
    sys.exit(0)

if __name__ == "__main__":
    main()