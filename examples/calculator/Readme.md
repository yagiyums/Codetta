# Calculator example

Run from the repository root with Python 3.10 or later. No dependencies are required.

```powershell
python -m conductor --input examples/calculator/expression.txt -o examples/calculator/score.svg
python -m performer examples/calculator/score.svg --no-play
```

The second command reads only the saved score and prints `16`.
Open `score.svg` in a browser to see the notes and nested enclosures.

To play on Windows and show the active phrase:

```powershell
python -m performer examples/calculator/score.svg --trace
```

The 2-beat control phrase plays first, then the main phrases last 6 and 10 beats.
At 120 BPM the complete performance contains 18 beats (9 seconds); its value is 16.
Control phrases are audible but are not added to the result.

To export sound without using an audio device:

```powershell
python -m performer examples/calculator/score.svg --no-play --wav examples/calculator/performance.wav
```

Other expressions to try: `3 - 5`, `3 / 2`, `-(3 + 5)`, `(1 + 2) * (5 - 3)`, `5 * 0`.
For an expression beginning with `-`, put it after `--`, for example:

```powershell
python -m conductor -o negative.svg -- "-(3 + 5)"
```
