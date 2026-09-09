# Codetta v0.1 calculator demo

Run the complete demo from the repository root with Python 3.10 or later:

```powershell
.\.venv\Scripts\python.exe examples\calculator\demo.py
```

The demo compiles `(3 + 5) * 2` and creates:

- `program.codetta`: official notation-only Codetta source container
- `score.musicxml`: exchange file for MuseScore and other notation software
- `score.svg`: conventional engraved staff notation
- `score.html`: browser view with optional Debug mode and PDF printing
- `performance.wav`: the score played with simultaneous voices

It then reloads `program.codetta` through Performer and prints:

```text
Result: 16
```

The same flow can be run as separate commands:

```powershell
python -m conductor --input examples\calculator\expression.txt -o examples\calculator\program.codetta
python -m performer examples\calculator\program.codetta --no-play --wav examples\calculator\performance.wav
python -m rendering examples\calculator\program.codetta -o examples\calculator\score.html
python -m conductor --input examples\calculator\expression.txt -o examples\calculator\score.musicxml
```

`program.codetta` contains pitches, durations, voices, rests, ties, slurs, and
brackets. It does not contain the input expression, AST nodes, operation names,
or the calculated value `16`.
