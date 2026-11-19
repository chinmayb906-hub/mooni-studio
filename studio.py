
import os
import json
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(api_key=API_KEY)

PROMPT = """
Create an original 60-second cartoon episode for children.

Requirements:
- Create an original and entertaining story.
- Use friendly characters.
- Include six scenes.
- Include visual descriptions.
- Include narration.
- Include character dialogue.
- Give the story a happy ending.

Return valid JSON only:
{
  "title": "Episode title",
  "description": "Short description",
  "scenes": [
    {
      "scene": 1,
      "visual": "Scene description",
      "narration": "Narration text",
      "dialogue": "Character dialogue"
    }
  ]
}
"""

def generate_episode():
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=PROMPT
    )

    result = response.text.strip()

    if result.startswith("```"):
        result = result.split("\n", 1)[1]
        result = result.rsplit("```", 1)[0].strip()

    episode = json.loads(result)

    if not episode.get("title") or not episode.get("scenes"):
        raise ValueError("Generated episode is incomplete.")

    os.makedirs("output", exist_ok=True)

    with open("output/episode.json", "w", encoding="utf-8") as file:
        json.dump(episode, file, ensure_ascii=False, indent=2)

    print("Episode generated successfully!")
    print("Title:", episode["title"])
    print("Scenes:", len(episode["scenes"]))


if __name__ == "__main__":
    generate_episode()
