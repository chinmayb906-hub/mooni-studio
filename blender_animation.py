
import bpy
import os
import math
import json

OUT_DIR = "output/3dclips"

BLUE = (0.12, 0.35, 0.85, 1)
YELLOW = (1.0, 0.75, 0.1, 1)
PURPLE = (0.55, 0.25, 0.8, 1)
GREEN = (0.2, 0.7, 0.25, 1)
CYAN = (0.1, 0.8, 0.8, 1)
SKIN = (0.95, 0.72, 0.52, 1)
BLACK = (0.04, 0.04, 0.04, 1)

FPS = 12


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True

    bsdf = mat.node_tree.nodes.get("Principled BSDF")

    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.65

    return mat


def sphere(name, loc, scale, color):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=16,
        location=loc
    )

    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(
        material(name + "Mat", color)
    )

    bpy.ops.object.shade_smooth()
    return obj


def cylinder(name, loc, radius, depth, color):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=24,
        radius=radius,
        depth=depth,
        location=loc
    )

    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(
        material(name + "Mat", color)
    )

    return obj


def setup(frame_end):
    scene = bpy.context.scene

    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 100

    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    scene.world.color = (0.5, 0.5, 0.5)

    bpy.ops.object.camera_add(
        location=(0, -16, 5)
    )

    camera = bpy.context.object
    camera.rotation_euler = (
        math.radians(82), 0, 0
    )
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8
    scene.camera = camera

    bpy.ops.object.light_add(
        type="AREA",
        location=(0, -7, 7)
    )

    light = bpy.context.object
    light.data.energy = 2200
    light.data.shape = "DISK"
    light.data.size = 10

    scene.render.image_settings.color_mode = "RGB"


def ground():
    bpy.ops.mesh.primitive_plane_add(
        size=200,
        location=(0, 0, 0)
    )

    obj = bpy.context.object
    obj.name = "Ground"

    obj.data.materials.append(
        material("Grass", (0.25, 0.55, 0.25, 1))
    )


def animate_mouth(mouth, timing):
    for frame, value in enumerate(timing, 1):
        mouth.scale.z = max(
            0.015,
            0.015 + value * 0.18
        )

        mouth.keyframe_insert(
            data_path="scale",
            frame=frame
        )


def person(name, x, color, timing):
    sphere(
        name + "_Body",
        (x, 0, 1.5),
        (0.55, 0.35, 0.75),
        color
    )

    head = sphere(
        name + "_Head",
        (x, 0, 2.65),
        (0.65, 0.55, 0.65),
        SKIN
    )

    sphere(
        name + "_Hair",
        (x, 0.05, 3.1),
        (0.58, 0.5, 0.3),
        (0.12, 0.07, 0.04, 1)
    )

    for side in [-1, 1]:
        sphere(
            name + "_Eye",
            (x + side * 0.22, -0.48, 2.72),
            (0.12, 0.09, 0.15),
            (1, 1, 1, 1)
        )

        sphere(
            name + "_Pupil",
            (x + side * 0.22, -0.55, 2.72),
            (0.06, 0.04, 0.08),
            BLACK
        )

        arm = sphere(
            name + "_Arm",
            (x + side * 0.75, 0, 1.75),
            (0.18, 0.22, 0.55),
            color
        )

        arm.rotation_euler[1] = side * 0.3
        arm.keyframe_insert(
            data_path="rotation_euler",
            frame=1
        )

        arm.rotation_euler[1] = side * 0.8
        arm.keyframe_insert(
            data_path="rotation_euler",
            frame=24
        )

        arm.rotation_euler[1] = side * 0.3
        arm.keyframe_insert(
            data_path="rotation_euler",
            frame=48
        )

    for side in [-1, 1]:
        cylinder(
            name + "_Leg",
            (x + side * 0.25, 0, 0.55),
            0.18,
            0.9,
            (0.15, 0.15, 0.2, 1)
        )

    mouth = sphere(
        name + "_Mouth",
        (x, -0.53, 2.43),
        (0.16, 0.04, 0.015),
        BLACK
    )

    animate_mouth(mouth, timing)

    head.keyframe_insert(
        data_path="location",
        frame=1
    )

    head.location.z += 0.12

    head.keyframe_insert(
        data_path="location",
        frame=24
    )

    head.location.z -= 0.12

    head.keyframe_insert(
        data_path="location",
        frame=48
    )


def dog(name, x, timing):
    sphere(
        name + "_Body",
        (x, 0, 0.8),
        (0.65, 0.4, 0.4),
        (0.9, 0.85, 0.8, 1)
    )

    sphere(
        name + "_Head",
        (x, -0.1, 1.35),
        (0.5, 0.45, 0.45),
        (0.95, 0.9, 0.85, 1)
    )

    sphere(
        name + "_Ear",
        (x - 0.35, -0.1, 1.45),
        (0.18, 0.2, 0.3),
        (0.45, 0.25, 0.15, 1)
    )

    sphere(
        name + "_Ear",
        (x + 0.35, -0.1, 1.45),
        (0.18, 0.2, 0.3),
        (0.45, 0.25, 0.15, 1)
    )

    sphere(
        name + "_Nose",
        (x, -0.5, 1.25),
        (0.12, 0.1, 0.1),
        BLACK
    )

    mouth = sphere(
        name + "_Mouth",
        (x, -0.48, 1.12),
        (0.12, 0.04, 0.015),
        BLACK
    )

    animate_mouth(mouth, timing)


def bird(name, x, timing):
    sphere(
        name + "_Body",
        (x, 0, 1.3),
        (0.45, 0.35, 0.6),
        (0.15, 0.7, 0.2, 1)
    )

    sphere(
        name + "_Head",
        (x, 0, 1.9),
        (0.4, 0.35, 0.4),
        (0.2, 0.8, 0.25, 1)
    )

    beak = sphere(
        name + "_Beak",
        (x, -0.35, 1.8),
        (0.18, 0.2, 0.08),
        (1, 0.8, 0.1, 1)
    )

    animate_mouth(beak, timing)

    sphere(
        name + "_Eye",
        (x + 0.15, -0.3, 1.95),
        (0.08, 0.06, 0.1),
        BLACK
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(
        "output/episode.json",
        encoding="utf-8"
    ) as f:
        episode = json.load(f)

    scenes = episode.get("scenes", [])

    if not scenes:
        raise RuntimeError("No scenes found in episode.json")

    for i, data in enumerate(scenes, 1):

        timing_path = (
            f"output/voice/scene_{i:02d}.json"
        )

        if not os.path.exists(timing_path):
            raise RuntimeError(
                f"Audio timing file missing: {timing_path}"
            )

        with open(
            timing_path,
            encoding="utf-8"
        ) as f:
            timing = json.load(f)

        if not timing:
            raise RuntimeError(
                f"Audio timing data is empty for scene {i}"
            )

        frame_end = max(12, len(timing))

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

        setup(frame_end)
        ground()

        names = data.get("characters", [])
        positions = [-2, 0, 2]

        if not names:
            raise RuntimeError(
                f"No characters assigned to scene {i}"
            )

        
        character_colors = [
            BLUE,
            YELLOW,
            PURPLE
        ]

        for j, name in enumerate(names[:3]):
            original_name = str(name).strip()
            name = original_name.lower()
            x = positions[j]
            color = character_colors[j]

            if name == "golu":
                person("Golu", x, BLUE, timing)

            elif name == "tara":
                person("Tara", x, YELLOW, timing)

            elif name == "moti":
                dog("Moti", x, timing)

            elif name == "dadi":
                person("Dadi", x, PURPLE, timing)

            elif name == "aarav":
                person("Aarav", x, GREEN, timing)

            elif name == "meera":
                person("Meera", x, CYAN, timing)

            elif name == "chiku":
                dog("Chiku", x, timing)

            elif name == "bholu":
                bird("Bholu", x, timing)

            elif name in ("uncle bhola", "unclebhola"):
                person("UncleBhola", x, BLUE, timing)

            else:
                safe_name = "ExtraCharacter" + str(j + 1)
                print(
                    "Unknown character name:",
                    original_name,
                    "- creating fallback character"
                )
                person(safe_name, x, color, timing)

            name = str(name).lower()
            x = positions[j]

            if name == "golu":
                person("Golu", x, BLUE, timing)

            elif name == "tara":
                person("Tara", x, YELLOW, timing)

            elif name == "moti":
                dog("Moti", x, timing)

            elif name == "dadi":
                person("Dadi", x, PURPLE, timing)

            elif name == "aarav":
                person("Aarav", x, GREEN, timing)

            elif name == "meera":
                person("Meera", x, CYAN, timing)

            elif name == "chiku":
                dog("Chiku", x, timing)

            elif name == "bholu":
                bird("Bholu", x, timing)

            elif name == "uncle bhola":
                person("UncleBhola", x, BLUE, timing)

        scene = bpy.context.scene
        scene.frame_set(1)

        scene.render.filepath = os.path.join(
            OUT_DIR,
            f"scene_{i:02d}.mp4"
        )

        print("Rendering character scene:", i)
        print("Output path:", scene.render.filepath)
        print("Characters:", names)

        bpy.ops.render.render(animation=True)

        output_file = os.path.join(
            OUT_DIR,
            f"scene_{i:02d}.mp4"
        )

        if not os.path.exists(output_file):
            raise RuntimeError(
                "3D character video was not created."
            )

        if os.path.getsize(output_file) < 10000:
            raise RuntimeError(
                "3D character video is unexpectedly small."
            )

        print(
            "3D character video created:",
            output_file
        )


if __name__ == "__main__":
    main()
