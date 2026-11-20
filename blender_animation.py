
import bpy
import json
import os
import math

ROOT = os.getcwd()
EPISODE_FILE = os.path.join(ROOT, "output", "episode.json")
OUT_DIR = os.path.join(ROOT, "output", "3dclips")

FPS = 12
DURATION = 3
FRAMES = FPS * DURATION

os.makedirs(OUT_DIR, exist_ok=True)

with open(EPISODE_FILE, encoding="utf-8") as f:
    episode = json.load(f)

def mat(name, color):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    return m

BLUE = mat("Blue", (0.1, 0.3, 0.8))
YELLOW = mat("Yellow", (1, 0.7, 0.1))
WHITE = mat("White", (0.9, 0.9, 0.9))
GREEN = mat("Green", (0.1, 0.5, 0.2))
BROWN = mat("Brown", (0.4, 0.2, 0.1))
SKIN = mat("Skin", (0.7, 0.4, 0.25))
ORANGE = mat("Orange", (1, 0.35, 0.05))
PURPLE = mat("Purple", (0.5, 0.2, 0.7))
CYAN = mat("Cyan", (0.1, 0.6, 0.8))
RED = mat("Red", (0.8, 0.1, 0.1))
BLACK = mat("Black", (0.03, 0.03, 0.03))

def sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(material)
    return o

def cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(material)
    return o

def ground():
    cube("Ground", (0, 0, -0.3), (15, 15, 0.3), GREEN)

    cube("House", (-3, 3, 1), (1.4, 1.4, 1), BROWN)

    bpy.ops.mesh.primitive_cone_add(
        vertices=24, radius1=2, radius2=0,
        depth=1.5, location=(-3, 3, 2.5)
    )
    bpy.context.object.data.materials.append(RED)

    for x in [-5, 5]:
        cube("TreeTrunk", (x, 3, 1), (0.2, 0.2, 1), BROWN)
        sphere("TreeTop", (x, 3, 2.5), (1, 1, 1.2), GREEN)

def person(name, x, color):
    body = cube(name+"_body", (x, 0, 1.2), (0.35, 0.25, 0.5), color)
    head = sphere(name+"_head", (x, 0, 2), (0.4, 0.4, 0.4), SKIN)

    sphere(name+"_eye1", (x-0.15, -0.36, 2.05), (0.07, 0.06, 0.08), BLACK)
    sphere(name+"_eye2", (x+0.15, -0.36, 2.05), (0.07, 0.06, 0.08), BLACK)

    cube(name+"_leg1", (x-0.18, 0, 0.4), (0.1, 0.12, 0.4), BLACK)
    cube(name+"_leg2", (x+0.18, 0, 0.4), (0.1, 0.12, 0.4), BLACK)

    sphere(name+"_arm1", (x-0.45, 0, 1.2), (0.12, 0.12, 0.4), color)
    sphere(name+"_arm2", (x+0.45, 0, 1.2), (0.12, 0.12, 0.4), color)

    # Gentle body bounce
    for frame in range(1, FRAMES + 1, 6):
        body.location.z = 1.2 + 0.1 * math.sin(frame / 4)
        head.location.z = 2 + 0.1 * math.sin(frame / 4)
        body.keyframe_insert(data_path="location", frame=frame)
        head.keyframe_insert(data_path="location", frame=frame)

def dog(name, x):
    sphere(name+"_body", (x, 0, 0.6), (0.55, 0.35, 0.3), WHITE)
    sphere(name+"_head", (x+0.4, 0, 1), (0.35, 0.35, 0.35), WHITE)
    sphere(name+"_ear1", (x+0.2, 0, 1.3), (0.12, 0.12, 0.25), BROWN)
    sphere(name+"_ear2", (x+0.55, 0, 1.3), (0.12, 0.12, 0.25), BROWN)
    sphere(name+"_eye1", (x+0.3, -0.3, 1.05), (0.06, 0.05, 0.06), BLACK)
    sphere(name+"_eye2", (x+0.5, -0.3, 1.05), (0.06, 0.05, 0.06), BLACK)

def bird(name, x):
    sphere(name+"_body", (x, 0, 1), (0.35, 0.3, 0.45), GREEN)
    sphere(name+"_head", (x, 0, 1.5), (0.3, 0.3, 0.3), GREEN)
    sphere(name+"_beak", (x+0.3, -0.1, 1.45), (0.15, 0.15, 0.1), YELLOW)
    sphere(name+"_eye", (x+0.1, -0.28, 1.55), (0.06, 0.05, 0.06), BLACK)

def setup():
    scene = bpy.context.scene
    scene.render.resolution_x = 720
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 50
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = FRAMES

    # Blender version compatibility
    engines = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    engine_names = [e.identifier for e in engines]

    if "BLENDER_EEVEE_NEXT" in engine_names:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif "BLENDER_EEVEE" in engine_names:
        scene.render.engine = "BLENDER_EEVEE"
    else:
        scene.render.engine = "BLENDER_WORKBENCH"

    bpy.ops.object.light_add(type="SUN", location=(0, -5, 8))
    bpy.context.object.data.energy = 2

    bpy.ops.object.camera_add(location=(0, -12, 5))
    camera = bpy.context.object
    camera.rotation_euler = (math.radians(70), 0, 0)
    scene.camera = camera

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"

def main():
    setup()

    for i, data in enumerate(episode.get("scenes", []), 1):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

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
