
import bpy
import os
import math

OUT_DIR = "output/3dclips"

BLUE = (0.12, 0.35, 0.85, 1)
YELLOW = (1.0, 0.75, 0.1, 1)
PURPLE = (0.55, 0.25, 0.8, 1)
GREEN = (0.2, 0.7, 0.25, 1)
CYAN = (0.1, 0.8, 0.8, 1)

def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat

def sphere(name, loc, scale, color):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=16, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material(name + "Mat", color))
    bpy.ops.object.shade_smooth()
    return obj

def cylinder(name, loc, radius, depth, color):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=24, radius=radius, depth=depth, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material(name + "Mat", color))
    return obj

def setup():
    scene = bpy.context.scene

    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 360
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100

    scene.render.fps = 12
    scene.frame_start = 1
    scene.frame_end = 48

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

    scene.world.color = (0.5, 0.5, 0.5)

    bpy.ops.object.camera_add(location=(0, -12, 4))
    camera = bpy.context.object
    camera.rotation_euler = (math.radians(75), 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 9
    scene.camera = camera

    bpy.ops.object.light_add(
        type="AREA", location=(0, -5, 8)
    )
    light = bpy.context.object
    light.data.energy = 1500
    light.data.shape = "DISK"
    light.data.size = 8

def ground():
    bpy.ops.mesh.primitive_plane_add(
        size=200, location=(0, 0, 0)
    )
    obj = bpy.context.object
    obj.name = "Ground"
    obj.data.materials.append(
        material("Grass", (0.25, 0.55, 0.25, 1))
    )

def person(name, x, color):
    body = sphere(
        name + "_Body", (x, 0, 1.5), (0.55, 0.35, 0.75),
        color
    )

    head = sphere(
        name + "_Head", (x, 0, 2.65), (0.65, 0.55, 0.65),
        (0.95, 0.72, 0.52, 1)
    )

    sphere(
        name + "_Hair", (x, 0.05, 3.1),
        (0.58, 0.5, 0.3), (0.12, 0.07, 0.04, 1)
    )

    for side in [-1, 1]:
        sphere(
            name + "_Eye", (x + side*0.22, -0.48, 2.72),
            (0.12, 0.09, 0.15), (1, 1, 1, 1)
        )
        sphere(
            name + "_Pupil", (x + side*0.22, -0.55, 2.72),
            (0.06, 0.04, 0.08), (0.05, 0.05, 0.05, 1)
        )

        arm = sphere(
            name + "_Arm", (x + side*0.75, 0, 1.75),
            (0.18, 0.22, 0.55), color
        )

        arm.rotation_euler[1] = side * 0.3

        arm.keyframe_insert(data_path="rotation_euler", frame=1)
        arm.rotation_euler[1] = side * 0.8
        arm.keyframe_insert(data_path="rotation_euler", frame=24)
        arm.rotation_euler[1] = side * 0.3
        arm.keyframe_insert(data_path="rotation_euler", frame=48)

    for side in [-1, 1]:
        cylinder(
            name + "_Leg", (x + side*0.25, 0, 0.55),
            0.18, 0.9, (0.15, 0.15, 0.2, 1)
        )

    head.keyframe_insert(data_path="location", frame=1)
    head.location.z += 0.12
    head.keyframe_insert(data_path="location", frame=24)
    head.location.z -= 0.12
    head.keyframe_insert(data_path="location", frame=48)

def dog(name, x):
    sphere(
        name + "_Body", (x, 0, 0.8),
        (0.65, 0.4, 0.4), (0.9, 0.85, 0.8, 1)
    )

    sphere(
        name + "_Head", (x, -0.1, 1.35),
        (0.5, 0.45, 0.45), (0.95, 0.9, 0.85, 1)
    )

    sphere(
        name + "_Ear", (x-0.35, -0.1, 1.45),
        (0.18, 0.2, 0.3), (0.45, 0.25, 0.15, 1)
    )

    sphere(
        name + "_Ear", (x+0.35, -0.1, 1.45),
        (0.18, 0.2, 0.3), (0.45, 0.25, 0.15, 1)
    )

    sphere(
        name + "_Nose", (x, -0.5, 1.25),
        (0.12, 0.1, 0.1), (0.05, 0.05, 0.05, 1)
    )

def bird(name, x):
    sphere(
        name + "_Body", (x, 0, 1.3),
        (0.45, 0.35, 0.6), (0.15, 0.7, 0.2, 1)
    )

    sphere(
        name + "_Head", (x, 0, 1.9),
        (0.4, 0.35, 0.4), (0.2, 0.8, 0.25, 1)
    )

    sphere(
        name + "_Beak", (x, -0.35, 1.8),
        (0.18, 0.2, 0.15), (1, 0.8, 0.1, 1)
    )

    sphere(
        name + "_Eye", (x+0.15, -0.3, 1.95),
        (0.08, 0.06, 0.1), (0, 0, 0, 1)
    )

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open("output/episode.json", encoding="utf-8") as f:
        episode = __import__("json").load(f)

    for i, data in enumerate(episode.get("scenes", []), 1):

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

        setup()
        ground()

        names = data.get("characters", [])
        positions = [-2, 0, 2]

        for j, name in enumerate(names[:3]):
            name = str(name).lower()
            x = positions[j]

            if name == "golu":
                person("Golu", x, BLUE)
            elif name == "tara":
                person("Tara", x, YELLOW)
            elif name == "moti":
                dog("Moti", x)
            elif name == "dadi":
                person("Dadi", x, PURPLE)
            elif name == "aarav":
                person("Aarav", x, GREEN)
            elif name == "meera":
                person("Meera", x, CYAN)
            elif name == "chiku":
                dog("Chiku", x)
            elif name == "bholu":
                bird("Bholu", x)
            elif name == "uncle bhola":
                person("UncleBhola", x, BLUE)

        scene = bpy.context.scene

        scene.frame_set(1)
        scene.render.filepath = os.path.join(
            OUT_DIR, f"scene_{i:02d}.mp4"
        )

        bpy.ops.render.render(animation=True)
        print("Rendered scene", i)

if __name__ == "__main__":
    main()
