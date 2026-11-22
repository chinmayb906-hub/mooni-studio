"""Offline tests for Mooni Studio.

They need no API keys, no network, no Blender, gTTS or Gemini. FFmpeg is
required for the audio and video tests (they are skipped if it is missing).

Run from the repository root:  python -m unittest discover -s tests -v
"""

import importlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import wave
import zlib
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import mooni_common as common  # noqa: E402
import pixabay  # noqa: E402
import studio  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

CHARACTERS = common.load_characters()
LOOKUP = common.character_lookup(CHARACTERS["characters"])


def write_png_rgba(path, width, height, rect):
    """Write a transparent PNG with one opaque red rectangle (x, y, w, h)."""
    x, y, w, h = rect
    clear = b"\x00" + b"\x00\x00\x00\x00" * width
    solid = (
        b"\x00"
        + b"\x00\x00\x00\x00" * x
        + b"\xff\x20\x20\xff" * w
        + b"\x00\x00\x00\x00" * (width - x - w)
    )
    raw = b"".join(
        solid if y <= row < y + h else clear for row in range(height)
    )

    def chunk(kind, data):
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 1)))
        f.write(chunk(b"IEND", b""))


def fake_tts(text, path):
    """Stand-in for gTTS: a tone whose length depends on the text."""
    seconds = max(0.4, 0.07 * len(text))
    rate = 22050

    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        frames = bytearray()

        for n in range(int(rate * seconds)):
            value = int(9000 * math.sin(2 * math.pi * 220 * n / rate))
            frames += struct.pack("<h", value)

        out.writeframes(bytes(frames))


class CommonTests(unittest.TestCase):
    def test_norm_and_canonical_names(self):
        self.assertEqual(common.norm_name("Uncle Bhola"), "unclebhola")
        self.assertEqual(
            common.canonical_speaker("uncle bhola", LOOKUP), "Uncle Bhola"
        )
        self.assertEqual(
            common.canonical_speaker("UNCLEBHOLA", LOOKUP), "Uncle Bhola"
        )
        self.assertEqual(
            common.canonical_speaker("narrator", LOOKUP), common.NARRATOR
        )
        self.assertEqual(
            common.canonical_speaker("", LOOKUP), common.NARRATOR
        )
        self.assertIsNone(common.canonical_speaker("Villager", LOOKUP))

    def test_every_character_has_a_valid_design(self):
        for character in CHARACTERS["characters"]:
            design = character["design"]
            self.assertIn(design["kind"], ("human", "dog", "fox", "parrot"))
            self.assertTrue(0.75 <= design["pitch"] <= 1.5)

            colours = [
                v for k, v in design.items()
                if isinstance(v, str) and v.startswith("#")
            ]
            self.assertTrue(colours)

            for value in colours:
                red, green, blue, alpha = common.hex_to_linear(value)
                for channel in (red, green, blue):
                    self.assertTrue(0.0 <= channel <= 1.0)

    def test_hex_to_linear(self):
        self.assertEqual(common.hex_to_linear("#FFFFFF"), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(common.hex_to_linear("#000000")[:3], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(common.hex_to_linear("#808080")[0], 0.2158, 3)
        with self.assertRaises(ValueError):
            common.hex_to_linear("#FFF")

    def test_layout_keeps_everyone_inside_the_frame(self):
        half = common.VIEW_WIDTH / 2

        for count in range(1, common.MAX_CHARACTERS_PER_SCENE + 1):
            layout = common.scene_layout(count)
            self.assertEqual(len(layout), count)

            for x, scale in layout:
                reach = scale * common.SLOT_WIDTH / 2
                self.assertLessEqual(abs(x) + reach, half + 1e-9)

            xs = [x for x, _ in layout]
            self.assertEqual(xs, sorted(xs))
            self.assertAlmostEqual(sum(xs), 0.0)

    def test_view_width_matches_portrait_camera(self):
        # An orthographic camera's ortho_scale is the size of the longer
        # image side, which is the height of a portrait frame. The visible
        # width is therefore scale * 720 / 1280. The previous script used
        # ortho_scale 5.8 (3.26 units wide) but placed side characters at
        # x = -2 and +2, i.e. centred outside the frame.
        self.assertAlmostEqual(common.VIEW_WIDTH, 3.6)
        old_half_width = 5.8 * 720 / 1280 / 2
        self.assertGreater(2.0, old_half_width)

    def test_envelope_is_normalised_and_bounded(self):
        loud = [8000 if (i // 50) % 2 == 0 else 0 for i in range(24000)]
        env = common.normalise_envelope(
            common.rms_envelope(loud, 24000, 12)
        )
        self.assertEqual(len(env), 12)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in env))
        self.assertGreater(max(env), 0.9)

        silent = common.normalise_envelope(
            common.rms_envelope([0] * 24000, 24000, 12)
        )
        self.assertEqual(max(silent), 0.0)

    def test_segment_frames(self):
        self.assertEqual(common.segment_frames(0.0, 1.0), (1, 12))
        first, last = common.segment_frames(1.0, 1.01)
        self.assertEqual(first, 13)
        self.assertGreaterEqual(last, first)

    def test_only_the_speaker_moves_their_mouth(self):
        envelope = [0.5] * 20
        segments = [
            {"speaker": "Golu", "start_frame": 1, "end_frame": 8},
            {"speaker": "Uncle Bhola", "start_frame": 10, "end_frame": 15},
            {"speaker": "Narrator", "start_frame": 17, "end_frame": 20},
        ]
        tracks = common.mouth_tracks(
            ["Golu", "Tara", "Uncle Bhola"], segments, envelope, 20
        )

        self.assertTrue(all(v > 0 for v in tracks["Golu"][0:8]))
        self.assertTrue(all(v == 0 for v in tracks["Golu"][8:]))
        self.assertTrue(all(v == 0 for v in tracks["Tara"]))
        self.assertTrue(all(v > 0 for v in tracks["Uncle Bhola"][9:15]))
        self.assertTrue(all(v == 0 for v in tracks["Uncle Bhola"][:9]))
        # Narrator lines move nobody's mouth.
        for track in tracks.values():
            self.assertTrue(all(v == 0 for v in track[16:]))


class StudioTests(unittest.TestCase):
    def test_clean_json_strips_fences(self):
        self.assertEqual(studio.clean_json('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(studio.clean_json('```\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(studio.clean_json('  {"a": 1} '), '{"a": 1}')

    def test_prompt_lists_every_character_and_the_rules(self):
        prompt = studio.build_prompt(CHARACTERS)
        for character in CHARACTERS["characters"]:
            self.assertIn(character["name"], prompt)
        self.assertIn("Narrator", prompt)

    def episode(self, **scene):
        base = {
            "characters": ["Golu", "Tara"],
            "visual": "A sunny village",
            "stock_query": "village children playing",
            "narration": "एक दिन गाँव में",
            "dialogue": [
                {"speaker": "Golu", "text": "चलो खेलें!"},
                {"speaker": "Tara", "text": "हाँ चलो!"},
            ],
        }
        base.update(scene)
        return {"title": "T", "description": "D", "scenes": [base]}

    def test_valid_episode_passes_through(self):
        result = studio.validate_episode(self.episode(), LOOKUP)
        scene = result["scenes"][0]
        self.assertEqual(scene["scene"], 1)
        self.assertEqual(scene["characters"], ["Golu", "Tara"])
        self.assertEqual(scene["stock_query"], "village children playing")
        self.assertEqual(len(scene["dialogue"]), 2)

    def test_speakers_are_normalised_and_unknown_become_narrator(self):
        data = self.episode(dialogue=[
            {"speaker": "golu", "text": "नमस्ते"},
            {"speaker": "uncle bhola", "text": "आओ"},
            {"speaker": "Villager", "text": "वाह"},
        ])
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        speakers = [line["speaker"] for line in scene["dialogue"]]
        self.assertEqual(speakers, ["Golu", "Uncle Bhola", "Narrator"])
        # Speakers are always on screen.
        self.assertIn("Uncle Bhola", scene["characters"])
        self.assertNotIn("Villager", scene["characters"])

    def test_cast_is_capped_and_unknown_characters_dropped(self):
        data = self.episode(
            characters=["Golu", "Tara", "Moti", "Dadi", "Aarav", "Ghost"]
        )
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        self.assertEqual(len(scene["characters"]), common.MAX_CHARACTERS_PER_SCENE)
        self.assertNotIn("Ghost", scene["characters"])

    def test_missing_cast_falls_back_to_defaults(self):
        data = self.episode(characters=[], dialogue=[])
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        self.assertEqual(len(scene["characters"]), 2)

    def test_dialogue_as_string_and_bad_lines(self):
        data = self.episode(dialogue="सिर्फ़ एक पंक्ति")
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        self.assertEqual(scene["dialogue"][0]["speaker"], "Narrator")

        data = self.episode(dialogue=[5, None, {"speaker": "Golu", "text": ""}])
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        self.assertEqual(scene["dialogue"], [])

    def test_scene_without_any_speech_is_rejected(self):
        with self.assertRaises(ValueError):
            studio.validate_episode(
                self.episode(narration="", dialogue=[]), LOOKUP
            )

    def test_scene_count_is_capped_and_renumbered(self):
        data = self.episode()
        data["scenes"] = data["scenes"] * 7
        result = studio.validate_episode(data, LOOKUP)
        self.assertEqual(
            [s["scene"] for s in result["scenes"]],
            list(range(1, common.MAX_SCENES + 1)),
        )

    def test_stock_query_must_be_plain_english(self):
        data = self.episode(stock_query="गाँव के बच्चे")
        scene = studio.validate_episode(data, LOOKUP)["scenes"][0]
        self.assertEqual(scene["stock_query"], studio.DEFAULT_QUERY)

    def test_garbage_is_rejected(self):
        for bad in ([], "x", {"scenes": []}, {"scenes": "no"}, {"scenes": [1]}):
            with self.assertRaises(ValueError):
                studio.validate_episode(bad, LOOKUP)

    def test_missing_api_key_gives_clear_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                studio.make_client()


class PixabayTests(unittest.TestCase):
    def test_queries_are_unique_and_end_with_fallbacks(self):
        queries = pixabay.build_queries({
            "stock_query": "village",
            "visual": "A sunny village garden with flowers",
        })
        self.assertEqual(queries[0], "village")
        self.assertEqual(len(queries), len({q.lower() for q in queries}))
        for fallback in pixabay.FALLBACK_QUERIES:
            self.assertIn(fallback, queries)

    def test_short_clips_are_tried_last(self):
        hits = [{"duration": 3, "id": 1}, {"duration": 12, "id": 2}]
        self.assertEqual(pixabay.prefer_long_clips(hits)[0]["id"], 2)

    def test_pick_url_prefers_medium(self):
        hit = {"videos": {"large": {"url": "L"}, "medium": {"url": "M"}}}
        self.assertEqual(pixabay.pick_url(hit), "M")
        self.assertIsNone(pixabay.pick_url({"videos": {}}))

    def test_bad_api_key_is_fatal(self):
        response = mock.Mock(status_code=400)
        with mock.patch("requests.get", return_value=response):
            with self.assertRaises(pixabay.PixabayAuthError):
                pixabay.get_with_retry("u", api=True)

    def test_temporary_errors_are_retried(self):
        bad = mock.Mock(status_code=503)
        good = mock.Mock(status_code=200)
        good.raise_for_status = lambda: None
        with mock.patch("requests.get", side_effect=[bad, good]), \
                mock.patch("time.sleep"):
            self.assertIs(pixabay.get_with_retry("u", api=True), good)

    def test_missing_key_message(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PIXABAY_API_KEY"):
                pixabay.get_api_key()


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is required")
class VideoPipelineTests(unittest.TestCase):
    """Voice -> timing -> composite -> final video, with fake TTS and frames."""

    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        os.makedirs("output")

        self.episode = {
            "title": "Test",
            "scenes": [
                {
                    "characters": ["Golu", "Tara"],
                    "narration": "एक सुंदर सुबह थी",
                    "dialogue": [
                        {"speaker": "Golu", "text": "चलो खेलने चलें"},
                        {"speaker": "Tara", "text": "हाँ चलो चलें"},
                    ],
                },
                {
                    "characters": ["Moti", "Dadi", "Uncle Bhola", "Bholu"],
                    "narration": "",
                    "dialogue": [
                        {"speaker": "Dadi", "text": "बच्चो खाना खा लो"},
                        {"speaker": "Bholu", "text": "टें टें"},
                    ],
                },
            ],
        }

        with open("output/episode.json", "w", encoding="utf-8") as f:
            json.dump(self.episode, f, ensure_ascii=False)

        self.rv = importlib.import_module("render_video")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_voices(self):
        self.rv.generate_voices(tts=fake_tts)

    def timing(self, index):
        with open(f"output/voice/scene_{index:02d}.json", encoding="utf-8") as f:
            return json.load(f)

    def test_voice_and_timing_data(self):
        self.make_voices()

        for index in (1, 2):
            timing = self.timing(index)
            wav = f"output/voice/scene_{index:02d}.wav"
            duration = self.rv.media_duration(wav)

            self.assertAlmostEqual(duration, timing["duration"], delta=0.05)
            self.assertEqual(len(timing["envelope"]), timing["n_frames"])
            self.assertGreaterEqual(
                timing["n_frames"], math.ceil(duration * common.FPS)
            )

            previous_end = 0.0
            for segment in timing["segments"]:
                self.assertGreater(segment["end"], segment["start"])
                self.assertGreaterEqual(segment["start"], previous_end)
                self.assertLessEqual(segment["end_frame"], timing["n_frames"])
                previous_end = segment["end"]

        scene1 = self.timing(1)
        self.assertEqual(
            [s["speaker"] for s in scene1["segments"]],
            ["Narrator", "Golu", "Tara"],
        )
        # An empty narration must not create a segment.
        self.assertEqual(
            [s["speaker"] for s in self.timing(2)["segments"]],
            ["Dadi", "Bholu"],
        )

    def test_speech_envelope_is_loud_only_while_someone_talks(self):
        self.make_voices()
        timing = self.timing(1)
        quiet_gap = [
            f for f in range(
                timing["segments"][0]["end_frame"] + 1,
                timing["segments"][1]["start_frame"],
            )
        ]
        self.assertGreater(
            max(timing["envelope"][
                timing["segments"][1]["start_frame"]:
                timing["segments"][1]["end_frame"]
            ]),
            0.5,
        )
        tail = timing["envelope"][-3:]
        self.assertLess(max(tail), 0.2)
        for frame in quiet_gap:
            self.assertLess(timing["envelope"][frame - 1], 0.6)

    def test_pitch_changes_voice_but_not_length(self):
        os.makedirs("output/p")
        fake_tts("नमस्ते दोस्तों", "output/p/raw.mp3")
        self.rv.make_segment_wav("x", 1.0, "output/p/a.wav", tts=fake_tts)
        self.rv.make_segment_wav("x", 1.38, "output/p/b.wav", tts=fake_tts)
        long_a = self.rv.media_duration("output/p/a.wav")
        long_b = self.rv.media_duration("output/p/b.wav")
        self.assertAlmostEqual(long_a, long_b, delta=0.05)
        self.assertNotEqual(
            self.rv.read_pcm("output/p/a.wav"),
            self.rv.read_pcm("output/p/b.wav"),
        )

    def make_frames(self, index, n_frames, visible=True):
        folder = f"output/3dframes/scene_{index:02d}"
        os.makedirs(folder, exist_ok=True)
        rect = (200, 500, 300, 600) if visible else (0, 0, 0, 0)
        write_png_rgba(f"{folder}/frame_0001.png", 720, 1280, rect)
        for n in range(2, n_frames + 1):
            shutil.copy(
                f"{folder}/frame_0001.png", f"{folder}/frame_{n:04d}.png"
            )

    def make_stock_clip(self, index):
        os.makedirs("output/clips", exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                "-i", "testsrc2=s=640x360:d=1.5:r=25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                f"output/clips/scene_{index:02d}.mp4",
            ],
            check=True,
        )

    def test_final_video_with_and_without_stock_footage(self):
        self.make_voices()
        self.make_stock_clip(1)  # scene 2 has no clip -> plain background

        for index in (1, 2):
            self.make_frames(index, self.timing(index)["n_frames"])

        self.rv.finalize_video()

        final = "output/mooni_episode.mp4"
        info, video, audio = self.rv.probe_video(final)
        self.assertTrue(audio)
        self.assertEqual(
            (video[0]["width"], video[0]["height"]), (720, 1280)
        )

        expected = sum(self.rv.media_duration(
            f"output/voice/scene_{i:02d}.wav") for i in (1, 2))
        self.assertAlmostEqual(
            float(info["format"]["duration"]), expected, delta=0.5
        )

        # The character rectangle is visible over the footage / background.
        for scene in (1, 2):
            pixels = subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-ss", "0.5",
                    "-i", f"output/scenes/scene_{scene:02d}.mp4",
                    "-vf", "crop=4:4:350:800", "-frames:v", "1",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
                ],
                capture_output=True, check=True,
            ).stdout
            red, green, blue = pixels[0], pixels[1], pixels[2]
            self.assertGreater(red, 180)
            self.assertLess(green, 90)
            self.assertLess(blue, 90)

    def test_missing_or_empty_frames_are_reported(self):
        self.make_voices()
        timing = self.timing(1)

        with self.assertRaisesRegex(RuntimeError, "MISSING BLENDER FRAME"):
            self.rv.check_character_frames(
                "output/3dframes/scene_01", timing["n_frames"]
            )

        self.make_frames(1, timing["n_frames"], visible=False)
        with self.assertRaisesRegex(RuntimeError, "NO CHARACTERS VISIBLE"):
            self.rv.check_character_frames(
                "output/3dframes/scene_01", timing["n_frames"]
            )

        self.make_frames(1, timing["n_frames"], visible=True)
        self.rv.check_character_frames(
            "output/3dframes/scene_01", timing["n_frames"]
        )

    def test_corrupt_stock_clip_falls_back(self):
        os.makedirs("output/clips")
        with open("output/clips/scene_01.mp4", "wb") as f:
            f.write(b"not a video" * 2000)
        self.assertFalse(self.rv.usable_clip("output/clips/scene_01.mp4"))
        self.assertFalse(self.rv.usable_clip("output/clips/missing.mp4"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is required")
class BlenderScriptDryRun(unittest.TestCase):
    """Run blender_animation.py against a recording stub of bpy."""

    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        os.makedirs("output/voice")

        import bpy_stub

        self.bpy = bpy_stub.Bpy()
        sys.modules["bpy"] = self.bpy
        sys.modules.pop("blender_animation", None)

        self.rv = importlib.import_module("render_video")

        episode = {
            "scenes": [
                {
                    "characters": ["Golu", "Tara"],
                    "narration": "एक सुंदर सुबह थी",
                    "dialogue": [
                        {"speaker": "Golu", "text": "चलो खेलने चलें"},
                        {"speaker": "Tara", "text": "हाँ चलो चलें"},
                    ],
                },
                {
                    "characters": ["Moti", "Chiku", "Dadi"],
                    "narration": "",
                    "dialogue": [
                        {"speaker": "Dadi", "text": "बच्चो खाना खा लो"},
                        {"speaker": "Bholu", "text": "टें टें"},
                    ],
                },
            ]
        }

        with open("output/episode.json", "w", encoding="utf-8") as f:
            json.dump(episode, f, ensure_ascii=False)

        self.rv.generate_voices(tts=fake_tts)

    def tearDown(self):
        sys.modules.pop("bpy", None)
        sys.modules.pop("blender_animation", None)
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self):
        module = importlib.import_module("blender_animation")
        module.main()
        return module

    def test_renders_every_scene_and_frame(self):
        self.run_script()

        for index in (1, 2):
            with open(f"output/voice/scene_{index:02d}.json") as f:
                n_frames = json.load(f)["n_frames"]

            folder = f"output/3dframes/scene_{index:02d}"
            frames = sorted(os.listdir(folder))
            self.assertEqual(len(frames), n_frames)
            self.assertEqual(frames[0], "frame_0001.png")
            self.assertEqual(frames[-1], "frame_%04d.png" % n_frames)
            self.assertTrue(
                os.path.exists(f"output/3dframes/debug_scene_{index:02d}.png")
            )

    def test_transparent_orthographic_portrait_setup(self):
        self.run_script()
        render = self.bpy.scene.render
        self.assertTrue(render.film_transparent)
        self.assertEqual(render.resolution_x, 720)
        self.assertEqual(render.resolution_y, 1280)
        self.assertEqual(render.fps, common.FPS)
        self.assertEqual(self.bpy.scene.camera.data.type, "ORTHO")
        self.assertAlmostEqual(
            self.bpy.scene.camera.data.ortho_scale, common.VIEW_HEIGHT
        )

    def roots(self):
        return {
            o.name[:-5]: o for o in self.bpy.objects
            if o.kind == "empty_add"
        }

    def test_cast_layout_and_speakers(self):
        module = importlib.import_module("blender_animation")

        with open("output/voice/scene_02.json") as f:
            timing = json.load(f)
        with open("output/episode.json") as f:
            scene = json.load(f)["scenes"][1]

        # Bholu speaks but is not listed: the speaker must still be drawn,
        # and the cast stays capped at four.
        cast = module.resolve_cast(scene, timing, LOOKUP)
        self.assertEqual(len(cast), 4)
        self.assertIn("Moti", cast)

        module.render_scene(2, scene, timing, LOOKUP)
        roots = self.roots()
        self.assertEqual(sorted(roots), sorted(cast))

        layout = common.scene_layout(len(cast))
        half = common.VIEW_WIDTH / 2

        for position, name in enumerate(cast):
            x, scale = layout[position]
            height = LOOKUP[common.norm_name(name)]["design"]["height"]
            root = roots[name]

            self.assertAlmostEqual(root.keys[0][2][0], x)
            self.assertAlmostEqual(root.scale[0], scale * height)
            # The whole character (slot width) stays inside the frame.
            self.assertLessEqual(
                abs(x) + scale * common.SLOT_WIDTH / 2, half + 1e-9
            )

    def test_each_mouth_only_moves_for_its_own_speaker(self):
        module = importlib.import_module("blender_animation")

        with open("output/voice/scene_01.json") as f:
            timing = json.load(f)
        with open("output/episode.json") as f:
            scene = json.load(f)["scenes"][0]

        module.render_scene(1, scene, timing, LOOKUP)

        golu_segment = timing["segments"][1]
        tara_segment = timing["segments"][2]
        self.assertEqual(golu_segment["speaker"], "Golu")
        self.assertEqual(tara_segment["speaker"], "Tara")

        def mouth_heights(name):
            mouth = next(
                o for o in self.bpy.objects if o.name == f"{name}_Mouth"
            )
            return {
                frame: value[2]
                for path, frame, value in mouth.keys if path == "scale"
            }

        golu = mouth_heights("Golu")
        tara = mouth_heights("Tara")
        rest = 0.015

        def peak(heights, segment):
            return max(
                heights[f]
                for f in range(segment["start_frame"], segment["end_frame"] + 1)
            )

        # Every frame is keyed for both characters.
        self.assertEqual(sorted(golu), list(range(1, timing["n_frames"] + 1)))
        self.assertEqual(sorted(tara), list(range(1, timing["n_frames"] + 1)))

        # Each mouth opens during its own line and stays shut during the
        # other character's line.
        self.assertGreater(peak(golu, golu_segment), rest)
        self.assertGreater(peak(tara, tara_segment), rest)
        self.assertAlmostEqual(peak(golu, tara_segment), rest)
        self.assertAlmostEqual(peak(tara, golu_segment), rest)

    def test_blinking_and_bobbing_are_keyframed(self):
        module = importlib.import_module("blender_animation")

        with open("output/voice/scene_01.json") as f:
            timing = json.load(f)
        with open("output/episode.json") as f:
            scene = json.load(f)["scenes"][0]

        module.render_scene(1, scene, timing, LOOKUP)

        root = next(o for o in self.bpy.objects if o.name == "Golu_Root")
        paths = {path for path, _, _ in root.keys}
        self.assertEqual(paths, {"location", "rotation_euler"})

        eye = next(o for o in self.bpy.objects if o.name == "Golu_Eye-1")
        heights = [value[2] for path, _, value in eye.keys]
        self.assertLess(min(heights), max(heights) * 0.2)  # a blink closes it

    def test_every_character_kind_can_be_built(self):
        module = importlib.import_module("blender_animation")

        for character in CHARACTERS["characters"]:
            actor = module.build_actor(
                character["name"], character["design"], 0.0, 1.0
            )
            self.assertIsNotNone(actor.mouth, character["name"])
            self.assertEqual(len(actor.eyes), 4, character["name"])

    def scene_one(self):
        with open("output/voice/scene_01.json") as f:
            timing = json.load(f)
        with open("output/episode.json") as f:
            scene = json.load(f)["scenes"][0]
        return scene, timing

    def test_falls_back_to_workbench_when_the_first_render_is_empty(self):
        module = importlib.import_module("blender_animation")
        scene, timing = self.scene_one()
        engines = []

        def fake_check(path):
            engine = self.bpy.scene.render.engine
            engines.append(engine)
            if engine == "BLENDER_WORKBENCH":
                return 0.4, 0.5
            return 0.0, 0.0

        with mock.patch.object(module, "check_visible", fake_check):
            module.render_scene(1, scene, timing, LOOKUP)

        self.assertEqual(
            engines, ["BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"]
        )
        frames = os.listdir("output/3dframes/scene_01")
        self.assertEqual(len(frames), timing["n_frames"])

    def test_no_fallback_when_the_first_render_is_fine(self):
        module = importlib.import_module("blender_animation")
        scene, timing = self.scene_one()

        module.render_scene(1, scene, timing, LOOKUP)

        self.assertEqual(self.bpy.scene.render.engine, "BLENDER_EEVEE_NEXT")

    def test_empty_render_in_every_engine_stops_with_a_clear_error(self):
        module = importlib.import_module("blender_animation")
        scene, timing = self.scene_one()

        with mock.patch.object(module, "check_visible", lambda p: (0.0, 0.0)):
            with self.assertRaisesRegex(RuntimeError, "BLACK OR EMPTY"):
                module.render_scene(1, scene, timing, LOOKUP)

        self.assertFalse(os.path.exists("output/3dframes/scene_01/frame_0001.png"))


class VoiceRetryTests(unittest.TestCase):
    """gTTS is a free web service: retries must work without real network."""

    def fake_gtts_module(self, fail_times):
        calls = {"count": 0}

        class FakeGTTS:
            def __init__(self, text, lang):
                self.text = text

            def save(self, path):
                calls["count"] += 1
                if calls["count"] <= fail_times:
                    raise ConnectionError("429 Too Many Requests")
                with open(path, "wb") as f:
                    f.write(b"x" * 2000)

        module = types.ModuleType("gtts")
        module.gTTS = FakeGTTS
        return module, calls

    def test_retries_then_succeeds(self):
        import render_video

        module, calls = self.fake_gtts_module(fail_times=2)
        folder = tempfile.mkdtemp()

        with mock.patch.dict(sys.modules, {"gtts": module}), \
                mock.patch("time.sleep") as sleep:
            render_video.tts_to_file("नमस्ते", os.path.join(folder, "a.mp3"))

        shutil.rmtree(folder, ignore_errors=True)
        self.assertEqual(calls["count"], 3)
        self.assertGreaterEqual(sleep.call_count, 3)

    def test_gives_up_with_a_clear_error(self):
        import render_video

        module, calls = self.fake_gtts_module(fail_times=99)
        folder = tempfile.mkdtemp()

        with mock.patch.dict(sys.modules, {"gtts": module}), \
                mock.patch("time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "Voice generation failed"):
                render_video.tts_to_file(
                    "नमस्ते", os.path.join(folder, "a.mp3"), attempts=3
                )

        shutil.rmtree(folder, ignore_errors=True)
        self.assertEqual(calls["count"], 3)


if __name__ == "__main__":
    unittest.main()
