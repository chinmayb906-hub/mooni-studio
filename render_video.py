import os
import json
import time
import subprocess
from gtts import gTTS
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip

WIDTH, HEIGHT, FPS = 1280, 720, 24


def make_voice(text, path, attempts=4):
    for attempt in range(attempts):
        try:
            gTTS(text=text, lang="hi").save(path)
            return
        except Exception as error:
            print(f"Voice error ({type(error).__name__}): {error}")

            if attempt == attempts - 1:
                raise

            time.sleep(5 * (attempt + 1))


def fix_clip(source, target, duration):
    """Loop or trim the stock clip to the voice length and make it 1280x720."""
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}"
    )

    command = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", source,
        "-t", f"{duration + 0.2:.2f}",
        "-map", "0:v:0",
        "-an", "-sn", "-dn",
        "-vf", video_filter,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        target,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        print("ffmpeg could not process this clip:")
        print(result.stderr[-800:])
        return False

    return True


def main():
    with open("output/episode.json", "r", encoding="utf-8") as f:
        episode = json.load(f)

    os.makedirs("output/voice", exist_ok=True)
    os.makedirs("output/clips_fixed", exist_ok=True)

    final_scenes = []

    for i, scene in enumerate(episode.get("scenes", []), 1):
        narration = scene.get("narration", "")
        dialogue = scene.get("dialogue", "")
        text = narration + (" " + dialogue if dialogue else "")

        if not text.strip():
            text = "Welcome to our magical story!"

        voice_path = f"output/voice/scene_{i:02d}.mp3"
        make_voice(text, voice_path)
        audio = AudioFileClip(voice_path)

        original = f"output/clips/scene_{i:02d}.mp4"
        fixed = f"output/clips_fixed/scene_{i:02d}.mp4"

        video = None

        if os.path.exists(original) and fix_clip(original, fixed, audio.duration):
            video = VideoFileClip(fixed)

        if video is None:
            video = ColorClip(
                size=(WIDTH, HEIGHT),
                color=(30, 30, 60),
                duration=audio.duration
            )

        if video.duration > audio.duration:
            video = video.subclipped(0, audio.duration)

        video = video.with_audio(audio)
        final_scenes.append(video)

        print(f"Prepared scene {i}")

    if not final_scenes:
        raise RuntimeError("No scenes were created.")

    final_video = concatenate_videoclips(final_scenes, method="compose")

    final_video.write_videofile(
        "output/mooni_episode.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    )

    print("Mooni Studio video created successfully!")


if __name__ == "__main__":
    main()
