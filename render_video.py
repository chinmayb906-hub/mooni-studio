"""Voice, lip-sync timing and final video assembly for Mooni Studio.

python render_video.py voice   -> per-speaker voices + scene audio + timing JSON
python render_video.py final   -> composite Blender characters over footage,
                                  add audio and join the scenes
"""

import array
import json
import math
import os
import subprocess
import sys
import time
import wave

from mooni_common import (
    AUDIO_RATE,
    FPS,
    GAP_SECONDS,
    NARRATOR,
    OUTPUT_DIR,
    TAIL_SECONDS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    call_with_deadline,
    character_lookup,
    load_characters,
    normalise_envelope,
    rms_envelope,
    segment_frames,
    voice_pitch,
)

FALLBACK_LINE = "आइए एक नई कहानी सुनते हैं।"

# Seconds to wait after each successful voice request (be gentle with gTTS).
PAUSE_BETWEEN_VOICE_REQUESTS = 0.6

# Give up on one voice request after this many seconds (and retry), so a
# request that never answers can not freeze the workflow.
VOICE_DEADLINE_SECONDS = 45


def run(command, timeout=300):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n" + result.stderr[-3000:]
        )

    return result


def probe_video(path):
    if not os.path.isfile(path) or os.path.getsize(path) < 1000:
        raise RuntimeError("Video file missing or too small: " + path)

    result = run([
        "ffprobe", "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        path
    ])

    info = json.loads(result.stdout)
    streams = info.get("streams", [])

    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]

    if not video:
        raise RuntimeError("No video stream found: " + path)

    return info, video, audio


def media_duration(path):
    result = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])

    duration = float(result.stdout.strip())

    if duration <= 0:
        raise RuntimeError("Invalid duration: " + path)

    return duration


def check_visible_video(path):
    info, video, audio = probe_video(path)

    duration = float(info.get("format", {}).get("duration", 0))

    if duration <= 0:
        raise RuntimeError("Invalid video duration: " + path)

    print("Checking visible frames:", path)

    for fraction in (0.20, 0.50, 0.80):
        timestamp = max(0, duration * fraction)

        result = subprocess.run(
            [
                "ffmpeg", "-v", "error",
                "-ss", str(timestamp),
                "-i", path,
                "-frames:v", "1",
                "-vf", "scale=32:32",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "pipe:1"
            ],
            capture_output=True,
            timeout=60
        )

        if result.returncode != 0 or len(result.stdout) < 32 * 32 * 3:
            raise RuntimeError(
                "Could not read video frame at " + str(timestamp)
            )

        pixels = result.stdout
        brightness = sum(pixels) / len(pixels)

        variance = sum(
            (value - brightness) ** 2 for value in pixels
        ) / len(pixels)

        print(
            "Frame", fraction,
            "brightness:", round(brightness, 2),
            "variation:", round(variance, 2)
        )

        if brightness < 8 or variance < 3:
            raise RuntimeError(
                "BLACK OR EMPTY VIDEO DETECTED: " + path
            )

    return duration


def check_audio(path):
    info, video, audio = probe_video(path)

    if not audio:
        raise RuntimeError("No audio stream found: " + path)

    print("Audio stream verified:", path)


# --------------------------------------------------------------------------
# Voice
# --------------------------------------------------------------------------

def tts_to_file(text, path, attempts=4):
    """Speak Hindi text with gTTS and save it as an MP3.

    The free gTTS service can refuse requests that arrive too quickly (HTTP
    429), especially from cloud machines, so each success is followed by a
    short pause and failures are retried with a growing wait.
    """
    from gtts import gTTS

    last_error = None

    for attempt in range(attempts):
        try:
            call_with_deadline(
                lambda: gTTS(text=text, lang="hi").save(path),
                VOICE_DEADLINE_SECONDS
            )

            if os.path.exists(path) and os.path.getsize(path) >= 1000:
                time.sleep(PAUSE_BETWEEN_VOICE_REQUESTS)
                return

            raise RuntimeError("gTTS produced an empty file.")

        except Exception as error:
            last_error = error
            print(
                f"Voice attempt {attempt + 1} failed: "
                f"{type(error).__name__}: {error}",
                flush=True
            )

            if attempt < attempts - 1:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"Voice generation failed: {last_error}")


def make_segment_wav(text, pitch, wav_path, tts=tts_to_file):
    """Create a 24 kHz mono WAV for one line, pitch-shifted for the speaker.

    asetrate raises pitch and speed together; atempo then restores the
    original speed, so only the pitch changes.
    """
    raw_path = wav_path[:-4] + "_raw.mp3"

    tts(text, raw_path)

    filters = [f"aresample={AUDIO_RATE}"]

    if abs(pitch - 1.0) >= 0.01:
        filters += [
            f"asetrate={int(AUDIO_RATE * pitch)}",
            f"aresample={AUDIO_RATE}",
            f"atempo={1.0 / pitch:.4f}",
        ]

    run([
        "ffmpeg", "-y",
        "-i", raw_path,
        "-af", ",".join(filters),
        "-ac", "1",
        "-ar", str(AUDIO_RATE),
        "-c:a", "pcm_s16le",
        wav_path
    ])

    os.remove(raw_path)


def read_pcm(path):
    with wave.open(path, "rb") as audio:
        if (
            audio.getsampwidth() != 2
            or audio.getnchannels() != 1
            or audio.getframerate() != AUDIO_RATE
        ):
            raise RuntimeError("Unexpected audio format: " + path)

        return audio.readframes(audio.getnframes())


def scene_speech(scene):
    """Ordered list of (speaker, text) for one scene."""
    specs = []

    narration = (scene.get("narration") or "").strip()

    if narration:
        specs.append((NARRATOR, narration))

    for line in scene.get("dialogue", []):
        if not isinstance(line, dict):
            continue

        text = (line.get("text") or "").strip()

        if text:
            specs.append((line.get("speaker") or NARRATOR, text))

    if not specs:
        specs.append((NARRATOR, FALLBACK_LINE))

    return specs


def build_scene_audio(index, specs, lookup, voice_dir, tts=tts_to_file):
    """Speak every line, join them, and work out who talks when."""
    parts_dir = os.path.join(voice_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)

    gap = b"\x00\x00" * int(AUDIO_RATE * GAP_SECONDS)
    tail = b"\x00\x00" * int(AUDIO_RATE * TAIL_SECONDS)

    pcm = bytearray()
    segments = []

    for number, (speaker, text) in enumerate(specs, 1):
        part_path = os.path.join(
            parts_dir, f"scene_{index:02d}_{number:02d}.wav"
        )

        make_segment_wav(
            text, voice_pitch(speaker, lookup), part_path, tts
        )

        if pcm:
            pcm.extend(gap)

        start = len(pcm) / 2 / AUDIO_RATE
        pcm.extend(read_pcm(part_path))
        end = len(pcm) / 2 / AUDIO_RATE

        first, last = segment_frames(start, end)

        segments.append({
            "speaker": speaker,
            "text": text,
            "start": round(start, 3),
            "end": round(end, 3),
            "start_frame": first,
            "end_frame": last,
        })

    pcm.extend(tail)

    wav_path = os.path.join(voice_dir, f"scene_{index:02d}.wav")

    with wave.open(wav_path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(AUDIO_RATE)
        out.writeframes(bytes(pcm))

    samples = array.array("h")
    samples.frombytes(bytes(pcm))

    if sys.byteorder == "big":
        samples.byteswap()

    duration = len(samples) / AUDIO_RATE
    n_frames = int(math.ceil(duration * FPS)) + 1

    envelope = normalise_envelope(
        rms_envelope(samples, AUDIO_RATE, FPS)
    )

    if not envelope:
        raise RuntimeError("No audio timing data generated.")

    envelope = (envelope + [0.0] * n_frames)[:n_frames]

    timing = {
        "fps": FPS,
        "duration": round(duration, 3),
        "n_frames": n_frames,
        "envelope": envelope,
        "segments": segments,
    }

    timing_path = os.path.join(voice_dir, f"scene_{index:02d}.json")

    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False)

    return timing


def generate_voices(tts=tts_to_file):
    episode_path = OUTPUT_DIR + "/episode.json"

    if not os.path.exists(episode_path):
        raise RuntimeError("Missing output/episode.json")

    with open(episode_path, encoding="utf-8") as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("Episode contains no scenes.")

    lookup = character_lookup(load_characters()["characters"])

    voice_dir = OUTPUT_DIR + "/voice"
    os.makedirs(voice_dir, exist_ok=True)

    for i, scene in enumerate(scenes, 1):
        print("Generating voices for scene:", i)

        timing = build_scene_audio(
            i, scene_speech(scene), lookup, voice_dir, tts
        )

        print(
            f"Scene {i}: {timing['duration']}s, "
            f"{len(timing['segments'])} spoken lines"
        )

    print("VOICE AND TIMING DATA READY")


# --------------------------------------------------------------------------
# Video
# --------------------------------------------------------------------------

def usable_clip(path):
    """True if a downloaded stock clip exists and can be decoded."""
    if not os.path.isfile(path) or os.path.getsize(path) < 10000:
        return False

    try:
        probe_video(path)
        return True
    except Exception as error:
        print("Ignoring unusable stock clip:", path, error)
        return False


def check_character_frames(frames_dir, n_frames):
    """Make sure Blender produced frames and the characters are visible."""
    first = f"{frames_dir}/frame_0001.png"
    last = f"{frames_dir}/frame_{n_frames:04d}.png"

    for path in (first, last):
        if not os.path.isfile(path):
            raise RuntimeError("MISSING BLENDER FRAME: " + path)

    middle = f"{frames_dir}/frame_{max(1, n_frames // 2):04d}.png"

    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-i", middle,
            "-vf", "scale=90:160",
            "-frames:v", "1",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "pipe:1"
        ],
        capture_output=True,
        timeout=60
    )

    expected = 90 * 160 * 4

    if result.returncode != 0 or len(result.stdout) < expected:
        raise RuntimeError("Could not read Blender frame: " + middle)

    alpha = result.stdout[3:expected:4]
    coverage = sum(1 for value in alpha if value > 16) / len(alpha)

    print(f"Character coverage in {middle}: {coverage:.1%}")

    if coverage < 0.01:
        raise RuntimeError(
            "NO CHARACTERS VISIBLE in Blender frames: " + frames_dir
        )


def composite_scene(frames_dir, audio_path, background, output_path):
    """Overlay Blender character frames on footage and add the voice."""
    duration = media_duration(audio_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    size = f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}"

    if background:
        background_input = ["-stream_loop", "-1", "-i", background]
        background_filter = (
            f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            ":force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            "setsar=1,fps=24,format=yuv420p[bg]"
        )
    else:
        # No stock clip for this scene: plain sky with a grass strip.
        background_input = [
            "-f", "lavfi",
            "-i", f"color=c=0x8EC5F0:s={size}:r=24"
        ]
        background_filter = (
            "[0:v]drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.4"
            ":color=0x56A85A:t=fill,"
            "setsar=1,fps=24,format=yuv420p[bg]"
        )

    filter_complex = (
        background_filter + ";"
        "[1:v]format=rgba,fps=24[fg];"
        "[bg][fg]overlay=x=0:y=0:eof_action=repeat:format=auto,"
        "format=yuv420p[v]"
    )

    run([
        "ffmpeg", "-y",
        *background_input,
        "-framerate", str(FPS),
        "-start_number", "1",
        "-i", f"{frames_dir}/frame_%04d.png",
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a:0",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", str(AUDIO_RATE),
        "-ac", "1",
        "-movflags", "+faststart",
        output_path
    ], timeout=900)


def render_scene(index, timing):
    frames_dir = f"{OUTPUT_DIR}/3dframes/scene_{index:02d}"
    audio_path = f"{OUTPUT_DIR}/voice/scene_{index:02d}.wav"
    clip_path = f"{OUTPUT_DIR}/clips/scene_{index:02d}.mp4"
    output_path = f"{OUTPUT_DIR}/scenes/scene_{index:02d}.mp4"

    if not os.path.exists(audio_path):
        raise RuntimeError("Audio file is missing: " + audio_path)

    check_character_frames(frames_dir, timing["n_frames"])

    background = clip_path if usable_clip(clip_path) else None

    if background:
        print(f"Scene {index}: using stock footage {clip_path}")
    else:
        print(f"Scene {index}: no usable stock footage, using plain background")

    composite_scene(frames_dir, audio_path, background, output_path)

    check_visible_video(output_path)
    check_audio(output_path)

    print("Scene completed:", output_path)

    return output_path


def finalize_video():
    episode_path = OUTPUT_DIR + "/episode.json"

    if not os.path.exists(episode_path):
        raise RuntimeError("Missing episode.json")

    with open(episode_path, encoding="utf-8") as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("No scenes to render.")

    os.makedirs(OUTPUT_DIR + "/scenes", exist_ok=True)

    rendered = []

    for i in range(1, len(scenes) + 1):
        print("Finalizing scene:", i)

        timing_path = f"{OUTPUT_DIR}/voice/scene_{i:02d}.json"

        if not os.path.exists(timing_path):
            raise RuntimeError("Missing audio timing: " + timing_path)

        with open(timing_path, encoding="utf-8") as f:
            timing = json.load(f)

        rendered.append(render_scene(i, timing))

    concat_path = OUTPUT_DIR + "/concat.txt"

    with open(concat_path, "w", encoding="utf-8") as f:
        for path in rendered:
            safe = os.path.abspath(path).replace("'", "'\\''")
            f.write("file '" + safe + "'\n")

    final_path = OUTPUT_DIR + "/mooni_episode.mp4"

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_path,
        "-c", "copy",
        "-movflags", "+faststart",
        final_path
    ])

    check_visible_video(final_path)
    check_audio(final_path)

    print("================================")
    print("MOONI STUDIO VIDEO CREATED!")
    print(final_path)
    print("================================")


if __name__ == "__main__":
    # Show each message in the workflow log straight away.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "voice":
        generate_voices()

    elif mode == "final":
        finalize_video()

    else:
        raise RuntimeError("Use voice or final mode.")
