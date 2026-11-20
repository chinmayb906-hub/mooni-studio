
import os
import json
import time
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(api_key=API_KEY)

PRIMARY_MODEL = "gemini-3.8-flash"
BACKUP_MODEL = "gemini-2.5-flash"


def generate_with_retry(prompt, model, attempts=5):
    for attempt in range(attempts):
        try:
            print(f"Trying {model}, attempt {attempt + 1}/{attempts}")

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            if not response.text:
                raise ValueError("Gemini returned empty text.")

            return response.text.strip()

        except Exception as e:
            print(f"Generation error: {e}")

            if attempt < attempts - 1:
                wait_time = 15 * (2 ** attempt)
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"{model} failed after {attempts} attempts.")

    return None


def clean_json(text):
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    return text


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
- Write the story in simple Hindi.
- Make every scene visually descriptive.
- Give the story a happy and meaningful ending.

Return valid JSON only:
{{
  "title": "Episode title",
  "description": "Short description",
  "scenes": [
    {{
      "scene": 1,
      "characters": ["Golu", "Tara"],
      "visual": "Detailed visual description including character appearances and village setting",
      "narration": "Narration text",
      "dialogue": "Character dialogue"
    }}
  ]
}}
"""

    result = generate_with_retry(prompt, PRIMARY_MODEL)

    if result is None:
        print("Primary model failed. Trying backup model...")
        result = generate_with_retry(prompt, BACKUP_MODEL, attempts=3)

    if result is None:
        raise RuntimeError("Both Gemini models failed. Please try again later.")

    episode = json.loads(clean_json(result))

    if not episode.get("title") or not episode.get("scenes"):
        raise ValueError("Generated episode is incomplete.")

    if len(episode["scenes"]) != 6:
        raise ValueError("Episode must contain exactly 6 scenes.")

    os.makedirs("output", exist_ok=True)

    with open("output/episode.json", "w", encoding="utf-8") as f:
        json.dump(episode, f, ensure_ascii=False, indent=2)

    print("Mooni Studio story generated successfully!")
    print("Title:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    generate_episode()
