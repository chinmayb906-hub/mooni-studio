
import os
import json
import re
import requests

API_KEY = os.environ.get("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError("PIXABAY_API_KEY is missing.")

API_URL = "https://pixabay.com/api/videos/"


def main():
    with open("output/episode.json", "r", encoding="utf-8") as file:
        episode = json.load(file)

    os.makedirs("output/clips", exist_ok=True)
    downloaded = 0

    for index, scene in enumerate(episode.get("scenes", []), 1):
        words = re.findall(r"[A-Za-z0-9]+", scene.get("visual", ""))
        query = " ".join(words[:6]) or "cartoon nature"

        response = requests.get(
            API_URL,
            params={
                "key": API_KEY,
                "q": query,
                "per_page": 3,
                "safesearch": "true"
            },
            timeout=30
        )
        response.raise_for_status()

        hits = response.json().get("hits", [])
        if not hits:
            print(f"No video found for scene {index}")
            continue

        videos = hits[0].get("videos", {})
        video = videos.get("medium") or videos.get("small")

        if not video or not video.get("url"):
            continue

        clip = requests.get(video["url"], timeout=60)
        clip.raise_for_status()

        path = f"output/clips/scene_{index:02d}.mp4"
        with open(path, "wb") as file:
            file.write(clip.content)

        downloaded += 1
        print(f"Downloaded {path}")

    if downloaded == 0:
        raise RuntimeError("No Pixabay clips downloaded.")

    print(f"Downloaded {downloaded} clips successfully.")


if __name__ == "__main__":
    main()
