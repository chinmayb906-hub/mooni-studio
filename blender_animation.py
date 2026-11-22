"""Mooni Studio 3D character animation (run inside Blender).

    blender -b --python blender_animation.py

Reads output/episode.json and output/voice/scene_XX.json, builds the cast of
every scene from characters.json, animates it (each character's mouth only
moves while that character is speaking) and renders a transparent PNG
sequence to output/3dframes/scene_XX/frame_####.png. render_video.py then
composites those frames over the stock footage.
"""

import json
import math
import os
import random
import sys

import bpy

_HERE = (
    os.path.dirname(os.path.abspath(__file__))
    if "__file__" in globals()
    else os.getcwd()
)

for _path in (_HERE, os.getcwd()):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from mooni_common import (  # noqa: E402
    FPS,
    OUTPUT_DIR,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VIEW_HEIGHT,
    canonical_speaker,
    character_lookup,
    hex_to_linear,
    load_characters,
    mouth_tracks,
    norm_name,
    scene_layout,
)

FRAMES_DIR = OUTPUT_DIR + "/3dframes"

BLACK = (0.02, 0.02, 0.02, 1)
WHITE = (1, 1, 1, 1)
DARK = (0.04, 0.03, 0.03, 1)
CAMERA_Z = 2.4

_material_cache = {}


# --------------------------------------------------------------------------
# Small building blocks
# --------------------------------------------------------------------------

def material(color, roughness=0.7, alpha=1.0):
    key = (tuple(color), roughness, alpha)

    if key in _material_cache:
        return _material_cache[key]

    mat = bpy.data.materials.new("Mooni_%d" % len(_material_cache))
    mat.diffuse_color = color
    mat.use_nodes = True

    bsdf = mat.node_tree.nodes.get("Principled BSDF")

    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness

        if alpha < 1.0:
            bsdf.inputs["Alpha"].default_value = alpha

            # The attribute depends on the Blender version.
            for attribute, value in (
                ("blend_method", "BLEND"),
                ("surface_render_method", "BLENDED"),
            ):
                try:
                    setattr(mat, attribute, value)
                except (AttributeError, TypeError):
                    pass

    _material_cache[key] = mat
    return mat


def _finish(obj, name, root, smooth=True):
    obj.name = name

    if smooth:
        bpy.ops.object.shade_smooth()

    if root is not None:
        obj.parent = root

    return obj


def add_sphere(name, loc, scale, color, root, rotation=None, roughness=0.7):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=16, location=loc
    )
    obj = bpy.context.object
    obj.scale = scale

    if rotation:
        obj.rotation_euler = rotation

    obj.data.materials.append(material(color, roughness))
    return _finish(obj, name, root)


def add_cylinder(name, loc, radius, depth, color, root):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=24, radius=radius, depth=depth, location=loc
    )
    obj = bpy.context.object
    obj.data.materials.append(material(color))
    return _finish(obj, name, root, smooth=False)


def add_cone(name, loc, radius, depth, color, root, rotation=None):
    bpy.ops.mesh.primitive_cone_add(
        vertices=24, radius1=radius, radius2=0.0, depth=depth, location=loc
    )
    obj = bpy.context.object

    if rotation:
        obj.rotation_euler = rotation

    obj.data.materials.append(material(color))
    return _finish(obj, name, root)


def add_torus(name, loc, major, minor, color, root, rotation=None):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=32,
        minor_segments=12,
        location=loc
    )
    obj = bpy.context.object

    if rotation:
        obj.rotation_euler = rotation

    obj.data.materials.append(material(color))
    return _finish(obj, name, root)


def add_cube(name, loc, scale, color, root):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.scale = scale
    obj.data.materials.append(material(color))
    return _finish(obj, name, root, smooth=False)


class Actor:
    """One animated character."""

    def __init__(self, name, root):
        self.name = name
        self.root = root
        self.mouth = None
        self.mouth_rest = (0.1, 0.04, 0.015)
        self.mouth_gain = 0.17
        self.eyes = []   # (object, rest scale)
        self.limbs = []  # (object, side, rest angle, gain)


def make_root(name, x, scale):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(x, 0, 0))
    root = bpy.context.object
    root.name = name + "_Root"
    root.scale = (scale, scale, scale)
    return root


def add_eyes(actor, spread, y, z, size):
    """White eyeballs with pupils; both are scaled shut when blinking."""
    for side in (-1, 1):
        white_scale = (size, size * 0.75, size * 1.25)
        pupil_scale = (size * 0.5, size * 0.35, size * 0.65)

        white = add_sphere(
            f"{actor.name}_Eye{side}",
            (side * spread, y, z),
            white_scale, WHITE, actor.root
        )

        pupil = add_sphere(
            f"{actor.name}_Pupil{side}",
            (side * spread, y - 0.07, z),
            pupil_scale, BLACK, actor.root
        )

        actor.eyes.append((white, white_scale))
        actor.eyes.append((pupil, pupil_scale))


def set_mouth(actor, obj, rest, gain):
    actor.mouth = obj
    actor.mouth_rest = rest
    actor.mouth_gain = gain


# --------------------------------------------------------------------------
# Character builders (all driven by the "design" block in characters.json)
# --------------------------------------------------------------------------

def build_hair(actor, style, color):
    root = actor.root
    n = actor.name

    add_sphere(n + "_Hair", (0, 0.05, 3.1), (0.58, 0.5, 0.3), color, root)

    if style == "wavy":
        for i, x in enumerate((-0.3, 0.0, 0.3)):
            add_sphere(
                f"{n}_Wave{i}", (x, 0.0, 3.4), (0.22, 0.2, 0.18),
                color, root
            )

    elif style == "bun":
        add_sphere(n + "_Bun", (0, 0.12, 3.5), (0.25, 0.25, 0.25), color, root)

    elif style == "braids":
        for side in (-1, 1):
            for i, z in enumerate((2.5, 2.2, 1.9)):
                add_sphere(
                    f"{n}_Braid{side}_{i}",
                    (side * 0.6, 0.05, z),
                    (0.13, 0.13, 0.16), color, root
                )

    elif style == "shoulder":
        for side in (-1, 1):
            add_sphere(
                f"{n}_SideHair{side}",
                (side * 0.58, 0.05, 2.45),
                (0.15, 0.3, 0.55), color, root
            )


def build_human(name, d, root):
    actor = Actor(name, root)

    skin = hex_to_linear(d["skin"])
    hair = hex_to_linear(d["hair"])
    top = hex_to_linear(d["top"])
    bottom = hex_to_linear(d.get("bottom", d["top"]))
    accent = hex_to_linear(d["accent"]) if d.get("accent") else top
    extras = set(d.get("extras", []))
    legs = d.get("legs", "long")

    if legs == "skirt":
        add_sphere(
            name + "_Body", (0, 0, 1.3), (0.62, 0.42, 0.98), top, root
        )
    else:
        add_sphere(
            name + "_Body", (0, 0, 1.5), (0.55, 0.35, 0.75), top, root
        )

    if "waistcoat" in extras or "jacket" in extras:
        add_sphere(
            name + "_Vest", (0, -0.1, 1.55), (0.5, 0.3, 0.62), accent, root
        )

    for side in (-1, 1):
        if legs == "long":
            add_cylinder(
                f"{name}_Leg{side}", (side * 0.25, 0, 0.55),
                0.18, 0.9, bottom, root
            )
        elif legs == "shorts":
            add_cylinder(
                f"{name}_Short{side}", (side * 0.25, 0, 0.8),
                0.19, 0.5, bottom, root
            )
            add_cylinder(
                f"{name}_Shin{side}", (side * 0.25, 0, 0.28),
                0.14, 0.45, skin, root
            )
        else:
            add_cylinder(
                f"{name}_Shin{side}", (side * 0.25, 0, 0.28),
                0.14, 0.5, skin, root
            )

        add_sphere(
            f"{name}_Foot{side}", (side * 0.25, -0.1, 0.07),
            (0.2, 0.28, 0.1), DARK, root
        )

    add_sphere(
        name + "_Head", (0, 0, 2.65), (0.65, 0.55, 0.65), skin, root
    )

    build_hair(actor, d.get("hair_style", "short"), hair)

    if "hairband" in extras:
        add_sphere(
            name + "_Band", (0, 0, 3.0), (0.57, 0.5, 0.05), accent, root
        )

    add_eyes(actor, 0.22, -0.48, 2.72, 0.12)

    if "glasses" in extras:
        for side in (-1, 1):
            add_torus(
                f"{name}_Glasses{side}", (side * 0.22, -0.55, 2.72),
                0.16, 0.022, DARK, root, rotation=(math.pi / 2, 0, 0)
            )

    mouth = add_sphere(
        name + "_Mouth", (0, -0.53, 2.43), (0.16, 0.04, 0.015), BLACK, root
    )
    set_mouth(actor, mouth, (0.16, 0.04, 0.015), 0.17)

    if "moustache" in extras:
        add_sphere(
            name + "_Moustache", (0, -0.5, 2.54), (0.3, 0.05, 0.06),
            hair, root
        )

    for side in (-1, 1):
        arm = add_sphere(
            f"{name}_Arm{side}", (side * 0.75, 0, 1.75),
            (0.18, 0.22, 0.55), top, root
        )
        arm.rotation_euler[1] = side * 0.3
        actor.limbs.append((arm, side, 0.3, 0.5))

    return actor


def build_animal(name, d, root):
    actor = Actor(name, root)

    fur = hex_to_linear(d["fur"])
    second = hex_to_linear(d["fur_secondary"])
    accent = hex_to_linear(d["accent"]) if d.get("accent") else second
    extras = set(d.get("extras", []))
    fox = d.get("kind") == "fox"

    add_sphere(name + "_Body", (0, 0.1, 0.8), (0.65, 0.45, 0.45), fur, root)
    add_sphere(name + "_Head", (0, -0.1, 1.35), (0.5, 0.45, 0.45), fur, root)
    add_sphere(
        name + "_Muzzle", (0, -0.45, 1.22), (0.26, 0.2, 0.18), second, root
    )
    add_sphere(
        name + "_Nose", (0, -0.62, 1.28), (0.09, 0.07, 0.07), BLACK, root
    )

    add_eyes(actor, 0.2, -0.48, 1.45, 0.08)

    mouth = add_sphere(
        name + "_Mouth", (0, -0.6, 1.12), (0.12, 0.04, 0.015), BLACK, root
    )
    set_mouth(actor, mouth, (0.12, 0.04, 0.015), 0.12)

    for side in (-1, 1):
        if fox:
            add_cone(
                f"{name}_Ear{side}", (side * 0.28, -0.05, 1.82),
                0.17, 0.42, fur, root
            )
        else:
            add_sphere(
                f"{name}_Ear{side}", (side * 0.4, -0.05, 1.42),
                (0.16, 0.2, 0.34), second, root
            )

        add_cylinder(
            f"{name}_Paw{side}", (side * 0.3, -0.2, 0.25),
            0.12, 0.5, fur, root
        )

    if fox:
        add_sphere(
            name + "_Tail", (0.6, 0.4, 0.95), (0.26, 0.36, 0.26), fur, root
        )
        add_sphere(
            name + "_TailTip", (0.68, 0.55, 1.15), (0.17, 0.2, 0.17),
            second, root
        )
    else:
        add_sphere(
            name + "_Tail", (0.55, 0.45, 0.95), (0.14, 0.14, 0.3),
            fur, root, rotation=(0, 0.6, 0)
        )

    if "collar" in extras:
        add_torus(
            name + "_Collar", (0, -0.1, 1.08), 0.34, 0.045, accent, root
        )

    if "neckerchief" in extras:
        add_cone(
            name + "_Neckerchief", (0, -0.36, 1.05), 0.27, 0.34,
            accent, root, rotation=(math.pi, 0, 0)
        )

    return actor


def build_parrot(name, d, root):
    actor = Actor(name, root)

    fur = hex_to_linear(d["fur"])
    dark = hex_to_linear(d["fur_secondary"])
    beak = hex_to_linear(d.get("beak", "#FFC21A"))
    accent = hex_to_linear(d["accent"]) if d.get("accent") else beak
    extras = set(d.get("extras", []))

    add_sphere(name + "_Body", (0, 0, 1.3), (0.45, 0.35, 0.6), fur, root)
    add_sphere(name + "_Head", (0, 0, 1.9), (0.4, 0.35, 0.4), fur, root)
    add_sphere(name + "_Tail", (0, 0.3, 0.7), (0.18, 0.1, 0.5), dark, root)

    for side in (-1, 1):
        wing = add_sphere(
            f"{name}_Wing{side}", (side * 0.45, 0.05, 1.3),
            (0.12, 0.2, 0.45), dark, root
        )
        wing.rotation_euler[1] = side * 0.2
        actor.limbs.append((wing, side, 0.2, 0.6))

        add_cylinder(
            f"{name}_Foot{side}", (side * 0.15, 0, 0.35),
            0.05, 0.5, beak, root
        )

    add_eyes(actor, 0.17, -0.3, 1.95, 0.07)

    mouth = add_sphere(
        name + "_Beak", (0, -0.35, 1.78), (0.18, 0.2, 0.08), beak, root
    )
    set_mouth(actor, mouth, (0.18, 0.2, 0.08), 0.12)

    if "satchel" in extras:
        add_cube(
            name + "_Satchel", (0.42, -0.15, 1.0), (0.3, 0.14, 0.26),
            accent, root
        )

    return actor


def build_actor(name, design, x, scale):
    root = make_root(name, x, scale * float(design.get("height", 1.0)))
    kind = design.get("kind", "human")

    if kind in ("dog", "fox"):
        return build_animal(name, design, root)

    if kind == "parrot":
        return build_parrot(name, design, root)

    return build_human(name, design, root)


# --------------------------------------------------------------------------
# Animation
# --------------------------------------------------------------------------

def key_scale(obj, scale, frame):
    obj.scale = scale
    obj.keyframe_insert(data_path="scale", frame=frame)


def blink_frames(n_frames, rng):
    frames = []
    frame = rng.randint(6, 30)

    while frame < n_frames - 2:
        frames.append(frame)
        frame += rng.randint(30, 60)

    return frames


def animate_actor(actor, x, base_scale, track, n_frames, rng):
    """Keyframe mouth, blinking, body bob/sway and arm or wing movement."""
    mouth_x, mouth_y, mouth_z = actor.mouth_rest

    for frame in range(1, n_frames + 1):
        amp = track[frame - 1]

        if actor.mouth is not None:
            key_scale(
                actor.mouth,
                (mouth_x, mouth_y, mouth_z + amp * actor.mouth_gain),
                frame
            )

        for obj, side, rest, gain in actor.limbs:
            obj.rotation_euler[1] = side * (rest + gain * amp)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    phase = rng.uniform(0, math.tau)
    sway_phase = rng.uniform(0, math.tau)
    root = actor.root

    for frame in range(1, n_frames + 1):
        seconds = (frame - 1) / float(FPS)
        amp = track[frame - 1]

        bob = 0.035 * math.sin(math.tau * seconds / 1.4 + phase)
        root.location = (x, 0, (bob + 0.07 * amp) * base_scale)
        root.rotation_euler[1] = 0.04 * math.sin(
            math.tau * seconds / 2.3 + sway_phase
        )

        root.keyframe_insert(data_path="location", frame=frame)
        root.keyframe_insert(data_path="rotation_euler", frame=frame)

    closed_factor = 0.08
    blinks = blink_frames(n_frames, rng)

    for obj, rest in actor.eyes:
        key_scale(obj, rest, 1)

        for frame in blinks:
            key_scale(obj, rest, frame - 1)
            key_scale(obj, (rest[0], rest[1], rest[2] * closed_factor), frame)
            key_scale(obj, rest, frame + 1)

        key_scale(obj, rest, n_frames)


def add_shadow(x, scale):
    """Soft contact shadow under a character."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=12, location=(x, 0.1, 0.01)
    )
    shadow = bpy.context.object
    shadow.name = "Shadow"
    shadow.scale = (0.8 * scale, 0.4 * scale, 0.02)
    shadow.data.materials.append(
        material((0.02, 0.04, 0.02, 1), roughness=1.0, alpha=0.35)
    )


# --------------------------------------------------------------------------
# Scene set-up
# --------------------------------------------------------------------------

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for collection in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def setup(n_frames):
    scene = bpy.context.scene

    available = [
        e.identifier
        for e in scene.render.bl_rna.properties["engine"].enum_items
    ]

    if "BLENDER_EEVEE_NEXT" in available:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif "BLENDER_EEVEE" in available:
        scene.render.engine = "BLENDER_EEVEE"
    else:
        raise RuntimeError("No supported EEVEE engine: " + str(available))

    scene.render.resolution_x = VIDEO_WIDTH
    scene.render.resolution_y = VIDEO_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = n_frames

    # Fewer anti-aliasing samples keep rendering fast on machines without a
    # graphics card (such as GitHub's), with little visible difference.
    try:
        scene.eevee.taa_render_samples = 16
    except (AttributeError, TypeError):
        pass

    # Transparent background: the stock footage is added later by ffmpeg.
    scene.render.film_transparent = True

    scene.view_settings.view_transform = "Standard"

    # Look names differ between Blender versions; fall back to the default.
    try:
        scene.view_settings.look = "Medium High Contrast"
    except (TypeError, ValueError):
        pass

    world = bpy.data.worlds.new("MooniWorld")
    scene.world = world
    world.use_nodes = True

    background = world.node_tree.nodes.get("Background")

    if background:
        background.inputs["Color"].default_value = (0.75, 0.82, 0.95, 1)
        background.inputs["Strength"].default_value = 0.9

    # Orthographic, level camera: the visible area is exactly
    # VIEW_WIDTH x VIEW_HEIGHT world units (see mooni_common.scene_layout).
    bpy.ops.object.camera_add(location=(0, -20, CAMERA_Z))
    camera = bpy.context.object
    camera.rotation_euler = (math.pi / 2, 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = VIEW_HEIGHT
    camera.data.clip_start = 0.1
    camera.data.clip_end = 100
    scene.camera = camera

    # Key light from the front and above, softer fill from the other side.
    for name, strength, rotation in (
        ("KeyLight", 3.0, (math.radians(50), 0, math.radians(20))),
        ("FillLight", 1.0, (math.radians(70), 0, math.radians(-35))),
    ):
        bpy.ops.object.light_add(type="SUN", location=(0, -5, 8))
        light = bpy.context.object
        light.name = name
        light.data.energy = strength
        light.rotation_euler = rotation


def check_visible(path):
    """Check that the diagnostic still contains visibly lit characters.

    Returns (coverage, brightness): the share of non-transparent pixels, and
    the mean brightness of those pixels. Uses only the standard library, so
    it works in any Blender build and in the offline tests.
    """
    from array import array

    image = bpy.data.images.load(path, check_existing=False)

    try:
        width, height = image.size
        buffer = array("f", bytes(4 * width * height * 4))

        try:
            image.pixels.foreach_get(buffer)
        except (TypeError, ValueError):
            buffer = array("f", image.pixels[:])
    finally:
        bpy.data.images.remove(image)

    pixel_count = width * height
    visible_pixels = 0
    brightness_total = 0.0

    for red, green, blue, alpha in zip(
        buffer[0::4], buffer[1::4], buffer[2::4], buffer[3::4]
    ):
        if alpha > 0.05:
            visible_pixels += 1
            brightness_total += (red + green + blue) / 3.0

    if visible_pixels == 0 or pixel_count == 0:
        return 0.0, 0.0

    return visible_pixels / pixel_count, brightness_total / visible_pixels


def resolve_cast(data, timing, lookup):
    """Characters to draw: those listed for the scene plus any speakers."""
    known = {c["name"] for c in lookup.values()}
    names = []

    def add(raw):
        name = canonical_speaker(raw, lookup)

        if name in known and name not in names:
            names.append(name)

    for raw in data.get("characters", []):
        add(raw)

    for segment in timing.get("segments", []):
        add(segment.get("speaker"))

    return names[:4]


def characters_visible(coverage, brightness):
    return coverage >= 0.01 and brightness >= 0.02


def use_workbench(scene):
    """Switch to Blender's simple Workbench renderer.

    EEVEE can render a blank (black) picture on machines without a real
    graphics card. Workbench is far simpler and uses each material's plain
    colour, so the characters always show up (with flatter lighting).
    """
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"


def render_diagnostic(scene, debug_file, frame):
    """Render one still and return (coverage, brightness) of the characters."""
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = debug_file
    scene.frame_set(frame)

    print("Rendering diagnostic image:", debug_file,
          "with", scene.render.engine)
    bpy.ops.render.render(write_still=True)

    if not os.path.exists(debug_file) or os.path.getsize(debug_file) < 1000:
        raise RuntimeError("Diagnostic PNG missing or blank: " + debug_file)

    coverage, brightness = check_visible(debug_file)
    print("CHARACTER COVERAGE:", round(coverage, 3),
          "BRIGHTNESS:", round(brightness, 3))

    return coverage, brightness


def render_scene(index, data, timing, lookup):
    n_frames = int(timing["n_frames"])

    if n_frames < 2:
        raise RuntimeError("Scene %d has no frames." % index)

    names = resolve_cast(data, timing, lookup)

    if not names:
        names = [c["name"] for c in list(lookup.values())[:2]]

    clear_scene()
    setup(n_frames)

    layout = scene_layout(len(names))
    tracks = mouth_tracks(
        names, timing.get("segments", []),
        timing.get("envelope", []), n_frames
    )

    for position, name in enumerate(names):
        x, scale = layout[position]
        design = lookup[norm_name(name)].get("design") or {}

        add_shadow(x, scale * float(design.get("height", 1.0)))

        actor = build_actor(name, design, x, scale)

        animate_actor(
            actor, x, scale * float(design.get("height", 1.0)),
            tracks[name], n_frames,
            random.Random("%d-%s" % (index, name))
        )

    scene = bpy.context.scene

    frames_dir = os.path.abspath(f"{FRAMES_DIR}/scene_{index:02d}")
    os.makedirs(frames_dir, exist_ok=True)

    # Diagnostic still from the middle of the scene.
    debug_file = os.path.abspath(f"{FRAMES_DIR}/debug_scene_{index:02d}.png")
    middle = max(1, n_frames // 2)

    coverage, brightness = render_diagnostic(scene, debug_file, middle)

    if not characters_visible(coverage, brightness):
        print("The picture looks empty; retrying with the Workbench renderer.")
        use_workbench(scene)
        coverage, brightness = render_diagnostic(scene, debug_file, middle)

    if not characters_visible(coverage, brightness):
        raise RuntimeError(
            "BLACK OR EMPTY RENDER DETECTED. Characters are not visible."
        )

    print("Blender version:", bpy.app.version_string)
    print("Render engine:", scene.render.engine)
    print("Cast:", ", ".join(names))
    print("Objects:", len(scene.objects))

    # Transparent PNG sequence.
    scene.render.filepath = os.path.join(frames_dir, "frame_####")

    print("Rendering animation:", index, "frames:", n_frames)
    bpy.ops.render.render(animation=True)

    for frame in (1, n_frames):
        path = os.path.join(frames_dir, "frame_%04d.png" % frame)

        if not os.path.exists(path):
            raise RuntimeError("Blender did not create: " + path)

    print("SUCCESS: scene", index, "->", frames_dir)


def main():
    os.makedirs(FRAMES_DIR, exist_ok=True)

    lookup = character_lookup(load_characters()["characters"])

    with open(OUTPUT_DIR + "/episode.json", encoding="utf-8") as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("No scenes found in episode.json")

    for index, data in enumerate(scenes, 1):
        timing_path = f"{OUTPUT_DIR}/voice/scene_{index:02d}.json"

        if not os.path.exists(timing_path):
            raise RuntimeError("Missing audio timing: " + timing_path)

        with open(timing_path, encoding="utf-8") as f:
            timing = json.load(f)

        render_scene(index, data, timing, lookup)


if __name__ == "__main__":
    main()
