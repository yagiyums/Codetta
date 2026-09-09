# Calculator example

Run from the repository root with Python 3.10 or later.

## View conventional staff notation

Install the optional renderer once:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rendering.txt
```

```powershell
.\.venv\Scripts\python.exe -m conductor --input examples/calculator/expression.txt -o examples/calculator/score.html
```

Open `score.html` in a browser. Normal mode shows only engraved notation;
the Debug mode checkbox enables IR annotations. Print / Save PDF exports via
the browser. `score.svg` and `score.musicxml` are the corresponding display assets.

## Execute the program

Execution uses a separate file and needs no external dependencies.

```powershell
python -m conductor --input examples/calculator/expression.txt --format executable-svg -o examples/calculator/program.codetta.svg
python -m performer examples/calculator/program.codetta.svg --no-play
```

The second command reads only the saved score and prints `16`.
`program.codetta.svg` retains the legacy executable enclosures. It is not the normal staff view.

To play on Windows and show the active phrase:

```powershell
python -m performer examples/calculator/program.codetta.svg --trace
```

The 2-beat control phrase plays first, then the main phrases last 6 and 10 beats.
At 120 BPM the complete performance contains 18 beats (9 seconds); its value is 16.
Control phrases are audible but are not added to the result.

To export sound without using an audio device:

```powershell
python -m performer examples/calculator/program.codetta.svg --no-play --wav examples/calculator/performance.wav
```

Other expressions to try: `3 - 5`, `3 / 2`, `-(3 + 5)`, `(1 + 2) * (5 - 3)`, `5 * 0`.
For an expression beginning with `-`, put it after `--`, for example:

```powershell
python -m conductor --format executable-svg -o negative.codetta.svg -- "-(3 + 5)"
```
