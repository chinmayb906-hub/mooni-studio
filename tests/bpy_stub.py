
"""A tiny stand-in for Blender's `bpy` module.

It is NOT Blender: it only records what blender_animation.py asks for, so the
script's own logic (cast selection, layout, per-character mouth keyframes,
file paths) can be tested without Blender installed. Whether the real Blender
API accepts every call can only be proven by running Blender.
"""

import copy
import os
import types


class _Namespace(types.SimpleNamespace):
    def __getattr__(self, name):
        # Unknown attributes read as harmless numbers/namespaces.
        value = _Namespace()
        object.__setattr__(self, name, value)
        return value


class StubObject:
    _vector_names = ("location", "scale", "rotation_euler")

    def __init__(self, kind, location=(0, 0, 0)):
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "name", kind)
        object.__setattr__(self, "parent", None)
        object.__setattr__(self, "users", 1)
        object.__setattr__(self, "keys", [])
        object.__setattr__(self, "location", list(location))
        object.__setattr__(self, "scale", [1.0, 1.0, 1.0])
        object.__setattr__(self, "rotation_euler", [0.0, 0.0, 0.0])
        object.__setattr__(self, "data", _Namespace(materials=[]))
        self.data.materials = []

    def __setattr__(self, name, value):
        if name in self._vector_names:
            value = list(value)
        object.__setattr__(self, name, value)

    def keyframe_insert(self, data_path, frame):
        self.keys.append(
            (data_path, frame, copy.copy(getattr(self, data_path)))
        )


class _Materials(list):
    def new(self, name):
        material = _Namespace(
            name=name,
            node_tree=_Namespace(nodes={"Principled BSDF": _Bsdf()}),
        )
        self.append(material)
        return material


class _Bsdf:
    def __init__(self):
        self.inputs = {
            key: _Namespace(default_value=None)
            for key in ("Base Color", "Roughness", "Alpha")
        }


class _Worlds(list):
    def new(self, name):
        world = _Namespace(
            name=name,
            node_tree=_Namespace(
                nodes={
                    "Background": _Namespace(
                        inputs={
                            "Color": _Namespace(default_value=None),
                            "Strength": _Namespace(default_value=None),
                        }
                    )
                }
            ),
        )
        self.append(world)
        return world


class _Collection(list):
    def remove(self, block):
        super().remove(block)


class _Image:
    size = (4, 4)

    class pixels:  # noqa: N801
        @staticmethod
        def foreach_get(buffer):
            buffer[:] = 0.5


class _Images:
    def load(self, path, check_existing=False):
        return _Image()

    def remove(self, image):
        pass


class _Engine:
    def __init__(self, identifier):
        self.identifier = identifier


class Bpy(types.ModuleType):
    def __init__(self):
        super().__init__("bpy")
        self.app = _Namespace(version_string="stub")
        self.objects = []
        self.render_log = []

        render = _Namespace(
            bl_rna=_Namespace(
                properties={
                    "engine": _Namespace(
                        enum_items=[_Engine("BLENDER_EEVEE_NEXT")]
                    )
                }
            ),
            filepath="",
        )

        self.scene = _Namespace(
            render=render,
            view_settings=_Namespace(),
            frame_start=1,
            frame_end=1,
            camera=None,
            world=None,
        )
        self.scene.frame_set = lambda frame: None
        self.scene_objects = self.objects
        self.scene.objects = self.objects

        self.context = _Namespace(scene=self.scene, object=None)
        self.data = _Namespace(
            materials=_Materials(),
            worlds=_Worlds(),
            meshes=_Collection(),
            cameras=_Collection(),
            lights=_Collection(),
            images=_Images(),
        )
        self.ops = _Namespace(
            mesh=_Namespace(),
            object=_Namespace(),
            light=_Namespace(),
            render=_Namespace(),
        )

        for name in (
            "primitive_uv_sphere_add",
            "primitive_cylinder_add",
            "primitive_cone_add",
            "primitive_torus_add",
            "primitive_cube_add",
        ):
            setattr(self.ops.mesh, name, self._adder(name))

        self.ops.object.empty_add = self._adder("empty_add")
        self.ops.object.camera_add = self._adder("camera_add")
        self.ops.object.light_add = self._adder("light_add")
        self.ops.object.shade_smooth = lambda **kw: None
        self.ops.object.select_all = lambda **kw: None
        self.ops.object.delete = self._delete
        self.ops.render.render = self._render

    def _adder(self, kind):
        def add(**kwargs):
            obj = StubObject(kind, kwargs.get("location", (0, 0, 0)))
            self.objects.append(obj)
            self.context.object = obj
            return {"FINISHED"}

        return add

    def _delete(self, **kwargs):
        del self.objects[:]

    def _render(self, write_still=False, animation=False):
        path = self.scene.render.filepath

        if write_still:
            self._write(path)

        if animation:
            for frame in range(
                self.scene.frame_start, self.scene.frame_end + 1
            ):
                self._write(path.replace("####", "%04d" % frame) + ".png")

        self.render_log.append((write_still, animation, path))

    @staticmethod
    def _write(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(b"\x89PNG" + b"0" * 2000)
