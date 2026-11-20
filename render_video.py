import os
import json
from gtts import gTTS
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip

def main():
    with open("output/episode.json", "r", encoding="utf-8") as f:
        episode = json.load(f)

    os.makedirs("output/voice", exist_ok=True)

    final_scenes = []

    for i, scene in enumerate(episode.get("scenes", []), 1):
        narration = scene.get("narration", "")
        dialogue = scene.get("dialogue", "")
        text = narration + (" " + dialogue if dialogue else "")

        if not text.strip():
            text = "Welcome to our magical story!"

        voice_path = f"output/voice/scene_{i:02d}.mp3"

        tts = gTTS(text=text, lang="en")
        tts.save(voice_path)

        audio = AudioFileClip(voice_path)

        clip_path = f"output/clips/scene_{i:02d}.mp4"

        if os.path.exists(clip_path):
            video = VideoFileClip(clip_path)

            if video.duration >= audio.duration:
                video = video.subclipped(0, audio.duration)
            else:
                video = video.with_duration(audio.duration)

            video = video.without_audio()
        else:
            video = ColorClip(
                size=(1280, 720),
                color=(30, 30, 60),
                duration=audio.duration
            )

        video = video.with_audio(audio)
        final_scenes.append(video)

        print(f"Prepared scene {i}")

    if not final_scenes:
        raise RuntimeError("No scenes were created.")

    final_video = concatenate_videoclips(final_scenes, method="compose")

    os.makedirs("output", exist_ok=True)
    final_video.write_videofile(
        "output/mooni_episode.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    print("Video created: output/mooni_episode.mp4")

if __name__ == "__main__":
    main()
