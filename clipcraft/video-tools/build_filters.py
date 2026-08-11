#!/usr/bin/env python3
"""Build FFmpeg motion-effect filters for static-scene video rendering."""

import math

ALLOWED_MOTIONS = {'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'}
ALLOWED_TRANSITIONS = {'fade', 'crossfade', 'slide_left', 'slide_right'}


def build_motion_filter(motion, nf, width=1080, height=1920):
    """Return an FFmpeg zoompan filter string for a given motion."""
    if motion == 'zoom_in':
        return f"zoompan=z='min(zoom+0.01,1.15)':d={nf}:s={width}x{height}:fps=30"
    elif motion == 'zoom_out':
        return f"zoompan=z='if(eq(on,0),1.15,max(zoom-0.01,1.0))':d={nf}:s={width}x{height}:fps=30"
    elif motion == 'pan_left':
        shift = int(width * 0.1)
        return (f"zoompan=z='1.1':x='min(0,-{shift}+on*({shift}/{nf}))':"
                f"d={nf}:s={width}x{height}:fps=30")
    elif motion == 'pan_right':
        shift = int(width * 0.1)
        return (f"zoompan=z='1.1':x='max(0,{shift}-on*({shift}/{nf}))':"
                f"d={nf}:s={width}x{height}:fps=30")
    elif motion == 'pan_up':
        shift = int(height * 0.1)
        return (f"zoompan=z='1.1':y='min(0,-{shift}+on*({shift}/{nf}))':"
                f"d={nf}:s={width}x{height}:fps=30")
    elif motion == 'pan_down':
        shift = int(height * 0.1)
        return (f"zoompan=z='1.1':y='max(0,{shift}-on*({shift}/{nf}))':"
                f"d={nf}:s={width}x{height}:fps=30")
    else:
        return f"zoompan=z='1':d={nf}:s={width}x{height}:fps=30"


def build_scene_filter(scene_index, motion, duration, width=1080, height=1920, fps=30):
    """Build a complete zoompan filter string labeled for a filter chain."""
    nf = int(round(duration * fps))
    motion_filter = build_motion_filter(motion, nf, width, height)
    input_label = f"[{scene_index}:v]"
    output_label = f"[s{scene_index}]"
    return f"{input_label}{motion_filter}{output_label}", nf


def build_concat_string(scene_labels):
    """Build concat filter input string from scene labels."""
    labels_str = ''.join(scene_labels)
    return f"{labels_str}concat=n={len(scene_labels)}:v=1:a=0[vout]"