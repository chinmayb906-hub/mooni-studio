
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

    bpy.ops.object.camera_add(location=(0, -16, 5))
    camera = bpy.context.object
    camera.rotation_euler = (math.radians(82), 0, 0)
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
