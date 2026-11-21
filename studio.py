import json
import os
import re
import time

from mooni_common import (
    MAX_CHARACTERS_PER_SCENE,
    MAX_DIALOGUE_LINES,
    MAX_SCENES,
    NARRATOR,
    OUTPUT_DIR,
    canonical_speaker,
    character_lookup,
    load_characters,
)

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite"
]

DEFAULT_VISUAL = "Colorful Indian village"
DEFAULT_QUERY = "Indian village nature"


def clean_json(text):
    """Strip markdown code fences that models sometimes wrap around JSON."""
    text = (text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return text.strip()


def _clean_text(value, limit):
    text = " ".join(str(value or "").split())
    return text[:limit]


def _clean_query(value, default):
    """Stock search queries must be plain English words."""
    text = re.sub(r"[^A-Za-z ]+", " ", str(value or ""))
    text = " ".join(text.split())[:60]
    return text or default


def validate_episode(data, lookup):
    """Normalise a model-written episode so later steps can trust it.

    - at most MAX_SCENES scenes, numbered 1..n
    - every speaker is a known character or Narrator
    - every scene has 1..MAX_CHARACTERS_PER_SCENE known on-screen characters
    - every scene has some spoken text
    """
    if not isinstance(data, dict):
        raise ValueError("Episode must be a JSON object.")

    scenes = data.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("No scenes found.")

    default_names = [
        c["name"] for c in list(lookup.values())[:2]
    ]

    cleaned = []

    for raw in scenes:
        if not isinstance(raw, dict):
            continue

        number = len(cleaned) + 1
        narration = _clean_text(raw.get("narration"), 300)

        dialogue_in = raw.get("dialogue", [])

        if isinstance(dialogue_in, str):
            dialogue_in = [{"speaker": NARRATOR, "text": dialogue_in}]

        if not isinstance(dialogue_in, list):
            dialogue_in = []

        dialogue = []

        for line in dialogue_in:
            if not isinstance(line, dict):
                continue

            text = _clean_text(line.get("text"), 200)

            if not text:
                continue

            speaker = canonical_speaker(line.get("speaker"), lookup)

            dialogue.append({
                "speaker": speaker or NARRATOR,
                "text": text
            })

            if len(dialogue) == MAX_DIALOGUE_LINES:
                break

        if not narration and not dialogue:
            raise ValueError(f"Scene {number} has no spoken text.")

        names = []

        def add(name):
            if (
                name
                and name != NARRATOR
                and name not in names
                and len(names) < MAX_CHARACTERS_PER_SCENE
            ):
                names.append(name)

        listed = raw.get("characters", [])

        if not isinstance(listed, list):
            listed = []

        for entry in listed:
            add(canonical_speaker(entry, lookup))

        for line in dialogue:
            add(line["speaker"])

        if not names:
            names = list(default_names)

        cleaned.append({
            "scene": number,
            "characters": names,
            "visual": _clean_text(raw.get("visual"), 300) or DEFAULT_VISUAL,
            "stock_query": _clean_query(
                raw.get("stock_query"), DEFAULT_QUERY
            ),
            "narration": narration,
            "dialogue": dialogue,
        })

        if len(cleaned) == MAX_SCENES:
            break

    if not cleaned:
        raise ValueError("No usable scenes found.")

    return {
        "title": _clean_text(data.get("title"), 100) or "Mooni Adventure",
        "description": (
            _clean_text(data.get("description"), 300)
            or "A magical children's story."
        ),
        "scenes": cleaned,
    }


def make_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY repository secret.")

    from google import genai

    return genai.Client(api_key=api_key)


def generate_story(prompt, lookup):
    from google.genai import types

    client = make_client()
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
                    json.loads(clean_json(response.text)),
                    lookup
                )

            except Exception as error:
                last_error = error
                print(f"Generation failed: {error}")

                if attempt == 0:
                    time.sleep(4)

    raise RuntimeError(
        f"All story generation attempts failed: {last_error}"
    )


def build_prompt(character_data):
    characters = character_data["characters"]

    character_details = "\n".join(
        f'{c["name"]}: {c["appearance"]}. '
        f'Personality: {c["personality"]}'
        for c in characters
    )

    names = ", ".join(c["name"] for c in characters)

    return f"""
Create an ORIGINAL high-quality children's cartoon episode.

STYLE:
{character_data["visual_style"]}

CHARACTERS:
{character_details}

RULES:
- Write the story in simple Hindi using Devanagari.
- Use no more than {MAX_SCENES} scenes.
- Use between 2 and {MAX_CHARACTERS_PER_SCENE} characters in every scene, and at least 3 different characters in the whole episode.
- Include a funny, magical or educational adventure.
- Keep character appearances consistent.
- Every scene must have English visual descriptions.
- Every scene must have an English stock video search query of 2 to 4 plain English words (a calm background such as a village, garden, river or sky; no people closeups).
- Every scene must have short Hindi narration (at most 25 words).
- Use separate speaker-labelled dialogue: 2 to {MAX_DIALOGUE_LINES} short lines per scene, each at most 15 words.
- The "speaker" of each dialogue line must be exactly one of: {names}, or Narrator.
- Every character who speaks must also be listed in that scene's "characters".
- Give a meaningful happy ending.
- Avoid violence, frightening scenes or inappropriate content.
- Make the story suitable for children aged 3 to 10.
- Avoid copyrighted characters and existing story plots.
- Keep the whole episode short enough for a YouTube Short (under 60 seconds when spoken).

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


def main():
    character_data = load_characters()
    lookup = character_lookup(character_data["characters"])

    episode = generate_story(build_prompt(character_data), lookup)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(
        OUTPUT_DIR + "/episode.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(episode, f, ensure_ascii=False, indent=2)

    print("Episode generated:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    main()
