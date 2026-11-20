import os
import json
import time
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. Add it in your repo: "
        "Settings > Secrets and variables > Actions > New repository secret."
    )

client = genai.Client(api_key=API_KEY)

# Tried in this order. If one is overloaded or unavailable, the next is used.
MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]

# Errors that retrying will not fix.
PERMANENT_ERRORS = (
    "404", "NOT_FOUND", "API_KEY_INVALID", "API key not valid",
    "PERMISSION_DENIED", "401", "403",
)


def clean_json(text):
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    return text


def parse_episode(text):
    episode = json.loads(clean_json(text))

    if not isinstance(episode, dict):
        raise ValueError("Gemini did not return a JSON object.")

    scenes = episode.get("scenes")

    if not episode.get("title") or not isinstance(scenes, list) or not scenes:
        raise ValueError("Generated episode is incomplete.")

    # Keep at most 6 scenes; accept fewer rather than failing the whole run.
    episode["scenes"] = scenes[:6]

    for number, scene in enumerate(episode["scenes"], 1):
        scene["scene"] = number
        scene.setdefault("narration", "")
        scene.setdefault("dialogue", "")
        scene.setdefault("visual", "")

    return episode


def generate_with_retry(prompt, model, attempts=4):
    last_error = None

    for attempt in range(attempts):
        try:
            print(f"Trying {model}, attempt {attempt + 1}/{attempts}")

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )

            if not response.text:
                raise ValueError("Gemini returned empty text.")

            return parse_episode(response.text), None

        except Exception as e:
            last_error = e
            print(f"Generation error ({type(e).__name__}): {e}")

            if any(code in str(e) for code in PERMANENT_ERRORS):
                print("Retrying will not fix this error. Moving on.")
                break

            if attempt < attempts - 1:
                wait_time = 10 * (2 ** attempt)
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)

    return None, last_error


def generate_episode():
    with open("characters.json", "r", encoding="utf-8") as f:
        character_data = json.load(f)

    characters = character_data["characters"]
    style = character_data["visual_style"]

    character_details = "\n".join(
        f'{c["name"]}: {c["appearance"]}. Personality: {c["personality"]}'
        for c in characters
    )

    prompt = f"""
Create an original, entertaining children's cartoon episode.

VISUAL STYLE:
{style}

PERMANENT CHARACTERS:
{character_details}

STORY REQUIREMENTS:
- Set the story in a colourful Indian village.
- Use Golu, Tara, Moti and Dadi as recurring characters.
- Keep their appearance and personalities consistent.
- Create an original mixed story: magic, comedy, adventure,
  friendship, education or moral lessons.
- Make the story suitable for children.
- Create exactly 6 scenes.
- Include narration and character dialogue.
- Write the narration and dialogue in simple Hindi (Devanagari script).
- Write the "visual" descriptions in English.
- Give every scene a "stock_query": two or three simple English words
  that describe the scene for a stock video search
  (for example: village children playing, grandmother cooking, puppy running).
- Give the story a happy and meaningful ending.

Return valid JSON only:
{{
  "title": "Episode title",
  "description": "Short description",
  "scenes": [
    {{
      "scene": 1,
      "characters": ["Golu", "Tara"],
      "visual": "Detailed English visual description including character appearances and village setting",
      "stock_query": "village children playing",
      "narration": "Narration text in Hindi",
      "dialogue": "Character dialogue in Hindi"
    }}
  ]
}}
"""

    episode = None
    last_error = None

    for model in MODELS:
        episode, error = generate_with_retry(prompt, model)

        if episode is not None:
            break

        last_error = error
        print(f"{model} did not work. Trying the next model...")

    if episode is None:
        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    os.makedirs("output", exist_ok=True)

    with open("output/episode.json", "w", encoding="utf-8") as f:
        json.dump(episode, f, ensure_ascii=False, indent=2)

    print("Mooni Studio story generated successfully!")
    print("Title:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    generate_episode()
