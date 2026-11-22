🌙 Mooni Studio — Lip Sync Episode Generator
Automated children's cartoon story and video generation project.

What it does
Story (studio.py) — Gemini writes an original Hindi episode (up to 4 scenes) using the cast in characters.json. The result is validated and cleaned: unknown speakers become the Narrator, every scene gets 1–4 known on-screen characters, speakers are always on screen.
Footage (pixabay.py) — one Pixabay background clip per scene. If a scene has no usable clip, a plain sky-and-grass background is used instead, so a missing clip never stops an episode. A wrong API key does stop the run.
Voices (render_video.py voice) — every line is spoken separately (Hindi gTTS) and pitch-shifted for its speaker (children higher, Dadi and Uncle Bhola lower). Lines are joined into one audio track per scene, with a timing file that records who speaks when and how loud.
Characters (blender_animation.py) — Blender builds each character from the design block in characters.json and renders a transparent PNG sequence. Each character's mouth moves only while that character is speaking; characters also blink, bob and sway, and arms or wings move while talking.
Final video (render_video.py final) — the character frames are composited over the footage, the voice is added, and the scenes are joined into one 720 x 1280 (9:16) MP4.
Characters
Golu, Tara, Moti, Dadi, Aarav, Meera, Chiku, Bholu and Uncle Bhola.

Each one is defined in characters.json:

appearance and personality are given to the story writer.
design controls the 3D model: kind (human, dog, fox, parrot), height, colours (#RRGGBB), hair_style (short, wavy, bun, braids, shoulder), legs (long, shorts, skirt), extras (glasses, moustache, waistcoat, jacket, hairband, collar, neckerchief, satchel) and the voice pitch (0.75–1.5).
To add a character, add an entry with a design block; no code changes are needed.

Required GitHub Secrets
GEMINI_API_KEY
PIXABAY_API_KEY
How to generate an episode
Open Actions.
Select Mooni Studio Lip Sync Episode Generator.
Click Run workflow.
Wait for the workflow.
Open the completed workflow.
Download the mooni-studio-lipsync-episode artifact.
Output
mooni_episode.mp4 — the finished episode
episode.json — the story
voice/scene_XX.wav and voice/scene_XX.json — scene audio and lip-sync timing
scenes/scene_XX.mp4 — each finished scene
3dframes/debug_scene_XX.png — a still of each scene's characters (check these first if something looks wrong)
Video format
720 x 1280 vertical video (YouTube Shorts / Instagram Reels).

Tests
The tests need no API keys, network or Blender (only FFmpeg):

python -m unittest discover -s tests -v
They run automatically at the start of every workflow run. They cover story validation, per-speaker voice and timing, per-character lip sync, compositing over footage, and a dry run of the Blender script against a recording stub (tests/bpy_stub.py).

Important
This engine uses AI-generated stories, text-to-speech voices and stock footage. The characters are simple stylised 3D figures built from basic shapes, not a full character-animation rig, and all voices come from one text-to-speech voice with different pitches.
