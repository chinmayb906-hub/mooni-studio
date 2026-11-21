"""Shared, dependency-free helpers for Mooni Studio.

Nothing in here imports bpy, network libraries or text-to-speech, so the same
code can be used by the story step, the voice step, the Blender step and the
tests.
"""

import json
import math
import os
import re

FPS = 12
OUTPUT_DIR = "output"
NARRATOR = "Narrator"

MAX_SCENES = 4
MAX_CHARACTERS_PER_SCENE = 4
MAX_DIALOGUE_LINES = 6

# Audio layout (seconds of silence between lines and after the last line).
GAP_SECONDS = 0.18
TAIL_SECONDS = 0.35
AUDIO_RATE = 24000

# Video / camera layout. The Blender camera is orthographic, so the visible
# world area is exactly VIEW_WIDTH x VIEW_HEIGHT units.
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
VIEW_HEIGHT = 6.4
VIEW_WIDTH = VIEW_HEIGHT * VIDEO_WIDTH / VIDEO_HEIGHT
SLOT_WIDTH = 1.9  # horizontal space one character needs at scale 1.0

_NARRATOR_KEYS = {"", "narrator", "narration", "storyteller"}
_HERE = os.path.dirname(os.path.abspath(__file__))


def norm_name(name):
    """Lower-case a name and strip everything except letters and digits."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def load_characters(path=None):
    path = path or os.path.join(_HERE, "characters.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("characters"):
        raise ValueError("characters.json contains no characters.")

    return data


def character_lookup(characters):
    """Map normalised name -> character dict."""
    return {norm_name(c["name"]): c for c in characters}


def canonical_speaker(name, lookup):
    """Return the canonical character name, NARRATOR, or None if unknown."""
    key = norm_name(name)

    if key in lookup:
        return lookup[key]["name"]

    if key in _NARRATOR_KEYS:
        return NARRATOR

    return None


def voice_pitch(speaker, lookup):
    """Pitch multiplier for a speaker (1.0 = unchanged)."""
    character = lookup.get(norm_name(speaker))

    if not character:
        return 1.0

    pitch = (character.get("design") or {}).get("pitch", 1.0)

    try:
        pitch = float(pitch)
    except (TypeError, ValueError):
        return 1.0

    return min(1.5, max(0.75, pitch))


def hex_to_linear(value, alpha=1.0):
    """Convert an sRGB hex colour such as '#C98E5F' to a linear RGBA tuple.

    Blender materials expect linear colour values.
    """
    text = str(value).strip().lstrip("#")

    if len(text) != 6:
        raise ValueError("Expected a colour like #RRGGBB, got: " + str(value))

    channels = []

    for start in (0, 2, 4):
        c = int(text[start:start + 2], 16) / 255.0
        channels.append(
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        )

    return (channels[0], channels[1], channels[2], alpha)


def scene_layout(count, view_width=VIEW_WIDTH, slot_width=SLOT_WIDTH):
    """Return [(x, scale), ...] so `count` characters fit inside the frame."""
    if count <= 0:
        return []

    slot = view_width / count
    scale = min(1.0, slot / slot_width)

    return [
        ((index - (count - 1) / 2.0) * slot, scale)
        for index in range(count)
    ]


def rms_envelope(samples, rate, fps=FPS):
    """Loudness (RMS) of each 1/fps chunk of 16-bit samples."""
    chunk = max(1, rate // fps)
    values = []

    for start in range(0, len(samples), chunk):
        block = samples[start:start + chunk]

        if len(block) == 0:
            continue

        values.append(
            math.sqrt(sum(s * s for s in block) / len(block))
        )

    return values


def smooth(values):
    """Light 3-tap smoothing so mouths do not flicker."""
    if len(values) < 3:
        return list(values)

    result = []

    for i, value in enumerate(values):
        before = values[i - 1] if i > 0 else value
        after = values[i + 1] if i < len(values) - 1 else value
        result.append(0.25 * before + 0.5 * value + 0.25 * after)

    return result


def normalise_envelope(raw):
    """Scale loudness to 0..1 relative to this scene's own loud passages."""
    active = sorted(v for v in raw if v > 300)

    if active:
        reference = active[int(len(active) * 0.9)]
    else:
        reference = 3000.0

    reference = max(reference, 1.0)

    scaled = [min(1.0, v / reference) for v in raw]

    return [round(min(1.0, max(0.0, v)), 3) for v in smooth(scaled)]


def segment_frames(start_seconds, end_seconds, fps=FPS):
    """1-based inclusive frame range covered by a spoken segment."""
    first = int(start_seconds * fps) + 1
    last = max(first, int(math.ceil(end_seconds * fps)))
    return first, last


def mouth_tracks(names, segments, envelope, n_frames):
    """Per-character mouth openness, one value per frame (frame 1 = index 0).

    A character's mouth only moves while that character is the speaker.
    """
    tracks = {}

    for name in names:
        key = norm_name(name)
        track = [0.0] * n_frames

        for segment in segments:
            if norm_name(segment.get("speaker")) != key:
                continue

            for frame in range(segment["start_frame"], segment["end_frame"] + 1):
                index = frame - 1

                if 0 <= index < n_frames:
                    value = envelope[index] if index < len(envelope) else 0.0
                    track[index] = max(track[index], value)

        tracks[name] = track

    return tracks
