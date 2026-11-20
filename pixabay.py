import os
import json
import re
import time
import requests

API_KEY = os.environ.get("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "PIXABAY_API_KEY is missing. Add it in your repo: "
        "Settings > Secrets and variables > Actions > New repository secret."
    )

API_URL = "https://pixabay.com/api/videos/"

# Used when a scene's own search words find nothing.
FALLBACK_QUERIES = ["village life", "children playing", "nature", "garden"]


# Pixabay sometimes answers 503 or 429 for a moment. Wait and try again.
RETRY_STATUS = {429, 500, 502, 503, 504}


def get_with_retry(url, params=None, timeout=30, attempts=5):
    last_error = None

    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as error:
            last_error = error
        else:
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


def search_videos(query):
    response = get_with_retry(
        API_URL,
        params={
            "key": API_KEY,
            "q": query,
            "per_page": 10,
            "safesearch": "true",
        },
        timeout=30,
    )
    return response.json().get("hits", [])


def pick_url(hit):
    videos = hit.get("videos", {})
    for size in ("medium", "small", "large", "tiny"):
        url = (videos.get(size) or {}).get("url")
        if url:
            return url
    return None


def main():
    with open("output/episode.json", "r", encoding="utf-8") as file:
        episode = json.load(file)

    os.makedirs("output/clips", exist_ok=True)
    downloaded = 0
    used_urls = set()

    for index, scene in enumerate(episode.get("scenes", []), 1):
        path = f"output/clips/scene_{index:02d}.mp4"
        saved = False

        for query in build_queries(scene):
            try:
                hits = search_videos(query)
            except requests.RequestException as error:
                print(f"Scene {index}: search failed for '{query}': {error}")
                continue

            for hit in hits:
                url = pick_url(hit)

                if not url or url in used_urls:
                    continue

                try:
                    clip = get_with_retry(url, timeout=90)
                except requests.RequestException as error:
                    print(f"Scene {index}: download failed: {error}")
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
            print(f"Scene {index}: no clip found, a plain background will be used.")

    if downloaded == 0:
        raise RuntimeError(
            "No Pixabay clips were downloaded. Check that PIXABAY_API_KEY is correct."
        )

    print(f"Downloaded {downloaded} clips successfully.")


if __name__ == "__main__":
    main()
