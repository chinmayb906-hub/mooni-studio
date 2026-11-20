
import os
import json
import subprocess
from gtts import gTTS
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip

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
        gTTS(text=text, lang="hi").save(voice_path)
        audio = AudioFileClip(voice_path)

        original = f"output/clips/scene_{i:02d}.mp4"
        fixed = f"output/clips_fixed/scene_{i:02d}.mp4"

        video = None

        if os.path.exists(original):
            command = [
                "ffmpeg", "-y", "-i", original,
                "-map", "0:v:0",
                "-an", "-sn", "-dn",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                fixed
            ]

            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            video = VideoFileClip(fixed)

        if video is None:
            video = ColorClip(
                size=(1280, 720),
                color=(30, 30, 60),
                duration=audio.duration
            )

        if video.duration >= audio.duration:
            video = video.subclipped(0, audio.duration)
        else:
            video = video.with_duration(audio.duration)

        video = video.with_audio(audio)
        final_scenes.append(video)

        print(f"Prepared scene {i}")

    if not final_scenes:
        raise RuntimeError("No scenes were created.")

    final_video = concatenate_videoclips(
        final_scenes,
        method="compose"
    )

    final_video.write_videofile(
        "output/mooni_episode.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    )

    print("Mooni Studio video created successfully!")

if __name__ == "__main__":
    main()
