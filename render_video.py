
import os
import json
import subprocess
from gtts import gTTS

WIDTH = 720
HEIGHT = 1280
FPS = 24


def run(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])


def make_voice(text, path):
    if not text.strip():
        text = "आइए एक नई कहानी सुनते हैं।"

    gTTS(text=text, lang="hi").save(path)


def render_scene(video_path, audio_path, output_path):
    audio_duration = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ],
            text=True
        ).strip()
    )

    filters = (
        "scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "setsar=1,"
        "fps=24"
    )

    if video_path and os.path.exists(video_path):
        command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", video_path,
            "-i", audio_path,
            "-t", str(audio_duration),
            "-vf", filters,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "27",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]
    else:
        command = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x182447:s=720x1280:r=24",
            "-i", audio_path,
            "-t", str(audio_duration),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "27",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]

    run(command)


def main():
    with open("output/episode.json", encoding="utf-8") as f:
        episode = json.load(f)

    os.makedirs("output/voice", exist_ok=True)
    os.makedirs("output/scenes", exist_ok=True)

    rendered = []

    for i, scene in enumerate(episode["scenes"], 1):
        print(f"Rendering scene {i}")

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

        voice_path = f"output/voice/scene_{i:02d}.mp3"
        scene_path = f"output/scenes/scene_{i:02d}.mp4"

        make_voice(text, voice_path)

        original = f"output/clips/scene_{i:02d}.mp4"
        animated_3d = f"output/3dclips/scene_{i:02d}.mp4"

        if os.path.exists(animated_3d):
            original = animated_3d

        source = original if os.path.exists(original) else None

        render_scene(
            source,
            voice_path,
            scene_path
        )

        rendered.append(scene_path)

    if not rendered:
        raise RuntimeError("No scenes were rendered.")

    with open("output/concat.txt", "w", encoding="utf-8") as f:
        for path in rendered:
            f.write(
                "file '" + os.path.abspath(path) + "'\n"
            )

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "output/concat.txt",
        "-c", "copy",
        "-movflags", "+faststart",
        "output/mooni_episode.mp4"
    ])

    print("FINAL VIDEO CREATED!")
    print("output/mooni_episode.mp4")


if __name__ == "__main__":
    main()
