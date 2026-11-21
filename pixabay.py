"""Download one Pixabay background clip per scene.

The clips are used as backgrounds behind the 3D characters. If no clip can be
found for a scene, render_video.py falls back to a plain sky-and-grass
background, so a missing clip never stops an episode. A wrong API key does
stop the run, because every scene would be affected.
"""

import json
import os
import re
import time

import requests

API_URL = "https://pixabay.com/api/videos/"

OUTPUT_DIR = "output"

# Used when a scene's own search words find nothing.
FALLBACK_QUERIES = ["village life", "nature", "garden", "countryside"]

# Pixabay sometimes answers 503 or 429 for a moment. Wait and try again.
RETRY_STATUS = {429, 500, 502, 503, 504}

# Status codes that mean the API key (or request) itself is wrong.
AUTH_STATUS = {400, 401, 403}

MIN_CLIP_BYTES = 10000


class PixabayAuthError(RuntimeError):
    """The API key was rejected."""


def get_api_key():
    key = os.environ.get("PIXABAY_API_KEY")

    if not key:
        raise RuntimeError(
            "PIXABAY_API_KEY is missing. Add it in your repo: "
            "Settings > Secrets and variables > Actions > New repository secret."
        )

    return key


def get_with_retry(url, params=None, timeout=30, attempts=5, api=False):
    last_error = None

    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as error:
            last_error = error
        else:
            if api and response.status_code in AUTH_STATUS:
                raise PixabayAuthError(
                    f"Pixabay rejected the request ({response.status_code}). "
                    "Check that PIXABAY_API_KEY is correct."
                )

            if response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response

            last_error = requests.HTTPError(
                f"{response.status_code} error from Pixabay"
            )

        if attempt < attempts - 1:
            wait_time = 5 * (attempt + 1)
            print(f"Pixabay problem ({last_error}). Retrying in {wait_time}s...")
            time.sleep(wait_time)

    raise last_error


def build_queries(scene):
    queries = []

    stock_query = (scene.get("stock_query") or "").strip()
    if stock_query:
        queries.append(stock_query)

    words = re.findall(r"[A-Za-z]+", scene.get("visual", ""))
    if len(words) >= 3:
        queries.append(" ".join(words[:3]))

    queries.extend(FALLBACK_QUERIES)

    seen = set()
    unique = []
    for query in queries:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            unique.append(query)

    return unique


def search_videos(query, api_key):
    response = get_with_retry(
        API_URL,
        params={
            "key": api_key,
            "q": query,
            "per_page": 10,
            "safesearch": "true",
        },
        timeout=30,
        api=True,
    )
    return response.json().get("hits", [])


def pick_url(hit):
    videos = hit.get("videos", {})
    for size in ("medium", "small", "large", "tiny"):
        url = (videos.get(size) or {}).get("url")
        if url:
            return url
    return None


def prefer_long_clips(hits):
    """Longer clips loop less noticeably; keep Pixabay's order otherwise."""
    return sorted(hits, key=lambda hit: (hit.get("duration") or 0) < 5)


def main():
    api_key = get_api_key()

    with open(OUTPUT_DIR + "/episode.json", "r", encoding="utf-8") as file:
        episode = json.load(file)

    os.makedirs(OUTPUT_DIR + "/clips", exist_ok=True)
    downloaded = 0
    used_urls = set()

    for index, scene in enumerate(episode.get("scenes", []), 1):
        path = f"{OUTPUT_DIR}/clips/scene_{index:02d}.mp4"
        saved = False

        for query in build_queries(scene):
            try:
                hits = search_videos(query, api_key)
            except requests.RequestException as error:
                print(f"Scene {index}: search failed for '{query}': {error}")
                continue

            for hit in prefer_long_clips(hits):
                url = pick_url(hit)

                if not url or url in used_urls:
                    continue

                try:
                    clip = get_with_retry(url, timeout=90)
                except requests.RequestException as error:
                    print(f"Scene {index}: download failed: {error}")
                    continue

                if len(clip.content) < MIN_CLIP_BYTES:
                    print(f"Scene {index}: clip too small, skipping.")
                    continue

                with open(path, "wb") as file:
                    file.write(clip.content)

                used_urls.add(url)
                downloaded += 1
                saved = True
                print(f"Scene {index}: downloaded {path} (search: '{query}')")
                break

            if saved:
                break

        if not saved:
            print(
                f"Scene {index}: no clip found, "
                "a plain background will be used."
            )

    print(f"Downloaded {downloaded} clips.")


if __name__ == "__main__":
    main()
