
import os
import json
import math
import subprocess
import wave
import struct
import sys

from gtts import gTTS

FPS = 12
OUTPUT_DIR = "output"


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
                "BLACK OR EMPTY VIDEO DETECTED: "
                + path
                + ". Blender may not have rendered visible characters."
            )

    return duration


def check_audio(path):
    info, video, audio = probe_video(path)

    if not audio:
        raise RuntimeError("No audio stream found: " + path)

    print("Audio stream verified:", path)


def make_voice(text, path):
    if not text.strip():
        text = "आइए एक नई कहानी सुनते हैं।"

    gTTS(text=text, lang="hi").save(path)

    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        raise RuntimeError("Voice generation failed: " + path)


def create_timing(audio_path, json_path, wav_path):
    run([
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ac", "1",
        "-ar", "12000",
        wav_path
    ])

    with wave.open(wav_path, "rb") as audio:
        rate = audio.getframerate()
        width = audio.getsampwidth()
        frames = audio.getnframes()
        raw = audio.readframes(frames)

    if width != 2:
        raise RuntimeError("Expected 16-bit audio.")

    samples = struct.unpack(
        "<" + "h" * (len(raw) // 2),
        raw
    )

    chunk = max(1, rate // FPS)
    values = []

    for start in range(0, len(samples), chunk):
        block = samples[start:start + chunk]

        if not block:
            continue

        rms = math.sqrt(
            sum(sample * sample for sample in block) / len(block)
        )

        values.append(round(min(1.0, rms / 7000.0), 3))

    if not values:
        raise RuntimeError("No audio timing data generated.")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(values, f)


def generate_voices():
    episode_path = OUTPUT_DIR + "/episode.json"

    if not os.path.exists(episode_path):
        raise RuntimeError("Missing output/episode.json")

    with open(episode_path, encoding="utf-8") as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("Episode contains no scenes.")

    os.makedirs(OUTPUT_DIR + "/voice", exist_ok=True)

    for i, scene in enumerate(scenes, 1):
        text_parts = []

        narration = scene.get("narration", "")
        if narration:
            text_parts.append(narration)

        for line in scene.get("dialogue", []):
            if isinstance(line, dict):
                spoken = line.get("text", "")
                if spoken:
                    text_parts.append(spoken)

        text = " ".join(text_parts)

        audio_path = f"output/voice/scene_{i:02d}.mp3"
        wav_path = f"output/voice/scene_{i:02d}.wav"
        timing_path = f"output/voice/scene_{i:02d}.json"

        print("Generating voice for scene:", i)

        make_voice(text, audio_path)

        create_timing(
            audio_path,
            timing_path,
            wav_path
        )

    print("VOICE AND TIMING DATA READY")


def render_scene(video_path, audio_path, output_path):
    if not os.path.exists(video_path):
        raise RuntimeError(
            "BLENDER CHARACTER VIDEO IS MISSING: " + video_path
        )

    if not os.path.exists(audio_path):
        raise RuntimeError("Audio file is missing: " + audio_path)

    check_visible_video(video_path)

    duration_result = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ])

    duration = float(duration_result.stdout.strip())

    if duration <= 0:
        raise RuntimeError("Invalid audio duration.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    filters = (
        "scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "setsar=1,"
        "fps=24"
    )

    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", video_path,
        "-i", audio_path,
        "-t", str(duration),
        "-vf", filters,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path
    ])

    check_visible_video(output_path)
    check_audio(output_path)

    print("Scene completed:", output_path)


def finalize_video():
    episode_path = OUTPUT_DIR + "/episode.json"

    if not os.path.exists(episode_path):
        raise RuntimeError("Missing episode.json")

    with open(episode_path, encoding="utf-8") as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("No scenes to render.")

    os.makedirs("output/scenes", exist_ok=True)

    rendered = []

    for i, scene in enumerate(scenes, 1):
        print("Finalizing scene:", i)

        audio_path = f"output/voice/scene_{i:02d}.mp3"
        video_path = f"output/3dclips/scene_{i:02d}.mp4"
        scene_path = f"output/scenes/scene_{i:02d}.mp4"

        render_scene(
            video_path,
            audio_path,
            scene_path
        )

        rendered.append(scene_path)

    with open("output/concat.txt", "w", encoding="utf-8") as f:
        for path in rendered:
            f.write("file '" + os.path.abspath(path) + "'\n")

    final_path = "output/mooni_episode.mp4"

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "output/concat.txt",
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
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "voice":
        generate_voices()

    elif mode == "final":
        finalize_video()

    else:
        raise RuntimeError("Use voice or final mode.")
