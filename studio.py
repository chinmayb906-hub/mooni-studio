
import os
import json
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(api_key=API_KEY)

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
- Include exactly 6 scenes.
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

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt
    )

    result = response.text.strip()

    if result.startswith("```"):
        result = result.split("\n", 1)[1]
        result = result.rsplit("```", 1)[0].strip()

    episode = json.loads(result)

    if not episode.get("title") or not episode.get("scenes"):
        raise ValueError("Generated episode is incomplete.")

    os.makedirs("output", exist_ok=True)

    with open("output/episode.json", "w", encoding="utf-8") as f:
        json.dump(episode, f, ensure_ascii=False, indent=2)

    print("Mooni Studio story generated!")
    print("Title:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    generate_episode()
