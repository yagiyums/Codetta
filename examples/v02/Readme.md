# Codetta v0.2 process example

This example is the v0.2 end-to-end acceptance program. It represents variables,
an array, a function section, a counted repeat, array access, a comparison and a
volta branch as score structures. It evaluates to `10`.

Generate `.codetta`, MusicXML, SVG, printable HTML and WAV artifacts:

```powershell
.\.venv\Scripts\python.exe .\examples\v02\demo.py
```

Run the saved notation directly:

```powershell
.\.venv\Scripts\python.exe -m performer .\examples\v02\program.codetta --no-play --trace
```

Open `program.codetta` with `Codetta Composer.cmd` to edit the ordinary score,
its Python projection and its notation-centered JSON projection together.
