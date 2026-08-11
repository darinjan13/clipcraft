#!/usr/bin/env python3
"""
Canonical asset path generator for the AI Video Factory.

Single source of truth for local filesystem paths.
Must produce identical output to PostgreSQL get_asset_path() and WF16 resolve-asset-paths.
"""

import json
import os
import re
from pathlib import Path, PurePosixPath

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
ASSET_TYPES = {
    'scene':       {'pattern': 'scene-{index:02d}.png'},
    'narration':   {'pattern': 'narration.wav'},
    'captions':    {'pattern': 'captions.ass'},
    'manifest':    {'pattern': 'render-manifest.json'},
    'video':       {'pattern': 'final.mp4'},
    'thumbnail':   {'pattern': 'thumbnail.jpg'},
    'render_log':  {'pattern': 'render.log'},
    'error_log':   {'pattern': 'error.log'},
}
ALLOWED_TYPES = set(ASSET_TYPES.keys())
BASE_DIR = '/data/jobs'
DOWNLOADABLE_TYPES = {'video', 'thumbnail', 'captions'}


def validate_uuid(job_id):
    value = str(job_id)
    if not UUID_RE.fullmatch(value):
        raise ValueError(f"Invalid job UUID: {job_id}")
    return value.lower()


def validate_asset_type(asset_type):
    if asset_type not in ALLOWED_TYPES:
        raise ValueError(f"Unknown asset type '{asset_type}'. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")


def validate_no_traversal(path):
    candidate = Path(path)
    root = Path(BASE_DIR)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path traversal detected: {path}") from exc
    return candidate.as_posix()


def validate_scene_index(scene_index):
    if scene_index is None:
        raise ValueError("scene_index required for asset_type 'scene'")
    if isinstance(scene_index, bool) or not isinstance(scene_index, int):
        raise TypeError('scene_index must be an integer')
    if not 1 <= scene_index <= 999:
        raise ValueError(f"scene_index out of range (1-999): {scene_index}")
    return scene_index


def _filename(asset_type, scene_index=None):
    validate_asset_type(asset_type)
    if asset_type == 'scene':
        return f"scene-{validate_scene_index(scene_index):02d}.png"
    return ASSET_TYPES[asset_type]['pattern']


def get_asset_key(job_id, asset_type, scene_index=None):
    canonical_job_id = validate_uuid(job_id)
    filename = _filename(asset_type, scene_index)
    return PurePosixPath(canonical_job_id, filename).as_posix()


def get_container_path(job_id, asset_type, scene_index=None, root=BASE_DIR):
    asset_key = get_asset_key(job_id, asset_type, scene_index)
    return (PurePosixPath(root) / PurePosixPath(asset_key)).as_posix()


def get_filesystem_path(job_id, asset_type, scene_index=None, root=BASE_DIR):
    asset_key = PurePosixPath(get_asset_key(job_id, asset_type, scene_index))
    native_root = Path(root)
    candidate = native_root.joinpath(*asset_key.parts)
    try:
        candidate.resolve().relative_to(native_root.resolve())
    except ValueError as exc:
        raise ValueError('Path traversal detected') from exc
    return candidate


def get_asset_path(job_id, asset_type, scene_index=None):
    canonical_job_id = validate_uuid(job_id)
    asset_key = get_asset_key(canonical_job_id, asset_type, scene_index)
    filename = PurePosixPath(asset_key).name
    safe_path = get_container_path(canonical_job_id, asset_type, scene_index)

    return {
        'path': safe_path,
        'asset_key': asset_key,
        'container_path': safe_path,
        'filename': filename,
        'job_id': canonical_job_id,
        'asset_type': asset_type,
    }


def get_asset_url(job_id, asset_type, base_url='/webhook/videos/download'):
    if asset_type not in DOWNLOADABLE_TYPES:
        raise ValueError(f"Asset type '{asset_type}' is not downloadable")
    return f"{base_url}?jobId={validate_uuid(job_id)}&asset={asset_type}"


def main():
    """CLI: python3 asset_paths.py <job_id> <asset_type> [scene_index]"""
    if len(sys.argv) < 3:
        print("Usage: asset_paths.py <job_id> <asset_type> [scene_index]", file=sys.stderr)
        sys.exit(1)
    job_id = sys.argv[1]
    asset_type = sys.argv[2]
    scene_index = int(sys.argv[3]) if len(sys.argv) > 3 else None
    result = get_asset_path(job_id, asset_type, scene_index)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    import sys
    main()
