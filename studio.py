
import os
import json
import time
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY repository secret.")

client = genai.Client(api_key=API_KEY)

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite"
]

MAX_SCENES = 4


def clean_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()
    return text


def validate_episode(data):
    if not isinstance(data, dict):
        raise ValueError("Episode must be a JSON object.")

    scenes = data.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("No scenes found.")

    data["scenes"] = scenes[:MAX_SCENES]

    for i, scene in enumerate(data["scenes"], 1):
        scene["scene"] = i
        scene.setdefault("visual", "Colorful Indian village")
        scene.setdefault("stock_query", "Indian village nature")
        scene.setdefault("narration", "")
        scene.setdefault("characters", [])

        dialogue = scene.get("dialogue", [])

        if isinstance(dialogue, str):
            dialogue = [{
                "speaker": "Narrator",
                "text": dialogue
            }]

        if not isinstance(dialogue, list):
            dialogue = []

        scene["dialogue"] = dialogue

        for line in dialogue:
            if not isinstance(line, dict):
                raise ValueError("Invalid dialogue format.")
            line.setdefault("speaker", "Narrator")
            line.setdefault("text", "")

    data.setdefault("title", "Mooni Adventure")
    data.setdefault("description", "A magical children's story.")

    return data


def generate_story(prompt):
    last_error = None

    for model in MODELS:
        for attempt in range(2):
            try:
                print(f"Trying {model}, attempt {attempt + 1}")

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.9
                    )
                )

                if not response.text:
                    raise ValueError("Empty response from Gemini.")

                return validate_episode(
                    json.loads(clean_json(response.text))
                )

            except Exception as error:
                last_error = error
                print(f"Generation failed: {error}")

                if attempt == 0:
                    time.sleep(4)

    raise RuntimeError(
        f"All story generation attempts failed: {last_error}"
    )


def main():
    with open("characters.json", encoding="utf-8") as f:
        character_data = json.load(f)

    characters = character_data["characters"]

    character_details = "\n".join(
        f'{c["name"]}: {c["appearance"]}. '
        f'Personality: {c["personality"]}'
        for c in characters
    )

    prompt = f"""
Create an ORIGINAL high-quality children's cartoon episode.

STYLE:
{character_data["visual_style"]}

CHARACTERS:
{character_details}

RULES:
- Write the story in simple Hindi using Devanagari.
- Use no more than 4 scenes.
- Use at least 3 recurring characters.
- Include a funny, magical or educational adventure.
- Keep character appearances consistent.
- Every scene must have English visual descriptions.
- Every scene must have an English stock video search query.
- Every scene must have Hindi narration.
- Use separate speaker-labelled dialogue.
- Allowed speaker names must match character names or Narrator.
- Give a meaningful happy ending.
- Avoid violence, frightening scenes or inappropriate content.
- Make the story suitable for children aged 3 to 10.
- Avoid copyrighted characters and existing story plots.
- Keep narration short enough for a YouTube Short.

Return valid JSON only:

{{
  "title": "Story title",
  "description": "Short story description",
  "scenes": [
    {{
      "scene": 1,
      "characters": ["Golu", "Tara"],
      "visual": "Detailed English visual description",
      "stock_query": "village children playing",
      "narration": "Hindi narration",
      "dialogue": [
        {{
          "speaker": "Golu",
          "text": "Hindi dialogue"
        }},
        {{
          "speaker": "Tara",
          "text": "Hindi dialogue"
        }}
      ]
    }}
  ]
}}
"""

    episode = generate_story(prompt)

    os.makedirs("output", exist_ok=True)

    with open(
        "output/episode.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(episode, f, ensure_ascii=False, indent=2)

    print("Episode generated:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    main()
