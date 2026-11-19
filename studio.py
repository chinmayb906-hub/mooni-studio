import os
import json
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(api_key=API_KEY)

PROMPT = """
Create an original short cartoon episode for children.

Requirements:
- Suitable for children.
- Original story.
- 60 seconds long.
- Friendly characters.
- Simple dialogue.
- Fun ending.
- 6 scenes.

Return JSON only, using this structure:
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

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=PROMPT
)

text = response.text.strip()

if text.startswith("```"):
    text = text.split("\n", 1)[1]
    text = text.rsplit("```", 1)[0].strip()

episode = json.loads(text)

os.makedirs("output", exist_ok=True)

with open("output/episode.json", "w", encoding="utf-8") as f:
    json.dump(episode, f, ensure_ascii=False, indent=2)

print("Episode script generated successfully!")
print("Title:", episode["title"])
