
"""
Advanced Blender bpy test stub for Mooni Studio.

Purpose:
- Simulate the bpy API used by blender_animation.py.
- Record created objects and keyframes.
- Simulate image loading and pixel access.
- Simulate still and animation rendering.
- Create placeholder output files for pipeline tests.

IMPORTANT:
This is NOT Blender. Real rendering must be tested using Blender.
"""

import copy
import os
import types
from array import array


class _Namespace(types.SimpleNamespace):
    """Automatically creates harmless placeholder attributes."""

    def __getattr__(self, name):
        value = _Namespace()
        object.__setattr__(self, name, value)
        return value


class StubObject:
    """Simple Blender-like object for offline tests."""

    _vector_names = (
        "location",
        "scale",
        "rotation_euler",
    )

    def __init__(self, kind, location=(0, 0, 0)):
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "name", kind)
        object.__setattr__(self, "parent", None)
        object.__setattr__(self, "users", 1)
        object.__setattr__(self, "keys", [])

        object.__setattr__(self, "location", list(location))
        object.__setattr__(self, "scale", [1.0, 1.0, 1.0])
        object.__setattr__(
            self,
            "rotation_euler",
            [0.0, 0.0, 0.0],
        )

        object.__setattr__(
            self,
            "data",
            _Namespace(materials=[]),
        )

    def __setattr__(self, name, value):
        if name in self._vector_names:
            value = list(value)

        object.__setattr__(self, name, value)

    def keyframe_insert(self, data_path, frame):
        value = getattr(self, data_path, None)

        self.keys.append(
            (
                data_path,
                frame,
                copy.copy(value),
            )
        )


class _Bsdf:
    def __init__(self):
        self.inputs = {
            key: _Namespace(default_value=None)
            for key in (
                "Base Color",
                "Roughness",
                "Alpha",
            )
        }


class _Materials(list):
    def new(self, name):
        material = _Namespace(
            name=name,
            node_tree=_Namespace(
                nodes={
                    "Principled BSDF": _Bsdf(),
                }
            ),
        )

        self.append(material)
        return material


class _Worlds(list):
    def new(self, name):
        world = _Namespace(
            name=name,
            node_tree=_Namespace(
                nodes={
                    "Background": _Namespace(
                        inputs={
                            "Color": _Namespace(
                                default_value=None
                            ),
                            "Strength": _Namespace(
                                default_value=None
                            ),
                        }
                    )
                }
            ),
        )

        self.append(world)
        return world


class _Collection(list):
    def remove(self, block):
        if block in self:
            super().remove(block)


class _Image:
    """Image placeholder with Blender-compatible pixel access."""

    def __init__(self, width=4, height=4):
        self.size = (width, height)
        self.channels = 4
        self.pixels = self._Pixels(width * height * 4)

    class _Pixels:
        def __init__(self, count):
            self.count = count

        def foreach_get(self, buffer):
            """
            Fill the supplied buffer safely.

            Supports Python arrays and mutable numeric sequences.
            Avoids the previous invalid array slice assignment.
            """
            if len(buffer) < self.count:
                raise ValueError(
                    "Pixel buffer is smaller than expected"
                )

            for i in range(self.count):
                buffer[i] = 0.5

        def __len__(self):
            return self.count


class _Images:
    def load(self, path, check_existing=False):
        if not os.path.exists(path):
            raise FileNotFoundError(
                "Image does not exist: " + str(path)
            )

        return _Image()

    def remove(self, image):
        pass


class _Engine:
    def __init__(self, identifier):
        self.identifier = identifier


class Bpy(types.ModuleType):
    """Minimal bpy module simulator."""

    def __init__(self):
        super().__init__("bpy")

        self.app = _Namespace(
            version_string="Mooni Studio Test Stub"
        )

        self.objects = []
        self.render_log = []

        render = _Namespace(
            bl_rna=_Namespace(
                properties={
                    "engine": _Namespace(
                        enum_items=[
                            _Engine("BLENDER_EEVEE_NEXT"),
                            _Engine("BLENDER_EEVEE"),
                        ]
                    )
                }
            ),
            filepath="",
            resolution_x=1920,
            resolution_y=1080,
            resolution_percentage=100,
            image_settings=_Namespace(
                file_format="PNG",
                color_mode="RGBA",
            ),
            film_transparent=False,
        )

        self.scene = _Namespace(
            render=render,
            view_settings=_Namespace(),
            frame_start=1,
            frame_end=1,
            frame_current=1,
            camera=None,
            world=None,
        )

        self.scene.frame_set = self._frame_set

        self.scene_objects = self.objects
        self.scene.objects = self.objects

        self.context = _Namespace(
            scene=self.scene,
            object=None,
            selected_objects=[],
            active_object=None,
        )

        self.data = _Namespace(
            objects=self.objects,
            materials=_Materials(),
            worlds=_Worlds(),
            meshes=_Collection(),
            cameras=_Collection(),
            lights=_Collection(),
            images=_Images(),
            collections=_Collection(),
        )

        self.ops = _Namespace(
            mesh=_Namespace(),
            object=_Namespace(),
            light=_Namespace(),
            render=_Namespace(),
            camera=_Namespace(),
            wm=_Namespace(),
        )

        mesh_operations = (
            "primitive_uv_sphere_add",
            "primitive_cylinder_add",
            "primitive_cone_add",
            "primitive_torus_add",
            "primitive_cube_add",
            "primitive_ico_sphere_add",
            "primitive_plane_add",
            "primitive_circle_add",
        )

        for name in mesh_operations:
            setattr(
                self.ops.mesh,
                name,
                self._adder(name),
            )

        self.ops.object.empty_add = self._adder("empty_add")
        self.ops.object.camera_add = self._adder("camera_add")
        self.ops.object.light_add = self._adder("light_add")

        self.ops.object.shade_smooth = lambda **kw: None
        self.ops.object.shade_flat = lambda **kw: None
        self.ops.object.select_all = self._select_all
        self.ops.object.delete = self._delete
        self.ops.object.transform_apply = lambda **kw: None
        self.ops.object.origin_set = lambda **kw: None

        self.ops.render.render = self._render

        self.ops.wm.save_as_mainfile = (
            lambda **kw: {"FINISHED"}
        )

    def _frame_set(self, frame):
        self.scene.frame_current = frame

    def _adder(self, kind):
        def add(**kwargs):
            location = kwargs.get(
                "location",
                (0, 0, 0),
            )

            obj = StubObject(kind, location)

            obj.name = kwargs.get(
                "name",
                kind,
            )

            self.objects.append(obj)
            self.context.object = obj
            self.context.active_object = obj
            self.context.selected_objects = [obj]

            return {"FINISHED"}

        return add

    def _select_all(self, **kwargs):
        self.context.selected_objects = list(self.objects)

    def _delete(self, **kwargs):
        self.objects.clear()
        self.context.object = None
        self.context.active_object = None
        self.context.selected_objects = []

    def _render(self, write_still=False, animation=False):
        path = self.scene.render.filepath

        if not path:
            raise ValueError(
                "Render output filepath is empty"
            )

        if write_still:
            self._write(path)

        if animation:
            for frame in range(
                self.scene.frame_start,
                self.scene.frame_end + 1,
            ):
                frame_path = path.replace(
                    "####",
                    "%04d" % frame,
                )

                if frame_path == path:
                    root, extension = os.path.splitext(path)
                    frame_path = (
                        root
                        + "_"
                        + "%04d" % frame
                        + (extension or ".png")
                    )

                self._write(frame_path)

        self.render_log.append(
            {
                "write_still": write_still,
                "animation": animation,
                "filepath": path,
                "frame_start": self.scene.frame_start,
                "frame_end": self.scene.frame_end,
            }
        )

    @staticmethod
    def _write(path):
        directory = os.path.dirname(path)

        if directory:
            os.makedirs(
                directory,
                exist_ok=True,
            )

        with open(path, "wb") as file:
            file.write(
                b"\x89PNG\r\n\x1a\n"
                + b"0" * 2000
            )
