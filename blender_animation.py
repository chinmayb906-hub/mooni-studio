def main():
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
