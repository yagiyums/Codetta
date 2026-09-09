# 通常の五線譜による表示

`rendering`はCodetta Score Modelを通常の楽譜として表示する層です。評価器やPerformerをImportせず、計算結果によって音価や配置を変更しません。

```text
.codetta → deserialize → Score Model → rendering.model
                                      → MusicXML 4.0
                                      → Verovio → SVG / HTML

MusicXML / MXL ───────────────────────→ Verovio → SVG / HTML
```

## 表示される情報

Score Modelの次の情報をMusicXMLへ移します。

- 五線、音部記号、調号、拍子記号、小節線
- 音符、休符、符幹、臨時記号、和音
- 開始位置、音価、付点、タイ
- 複数声部と同時配置
- 実線・破線のスラーと括弧線
- 最終小節の終止線

通常表示には値、演算名、AST、IR、計算結果、内部IDを出しません。Debug modeではScore Parserと対応するグループ種別を別のMusicXML/SVGへ注記し、HTML上で通常表示と切り替えます。Debug情報は`.codetta`へ保存しません。

## API

```python
from codetta.serialization import read_score
from rendering.musicxml import to_musicxml
from rendering.renderer import render_score, write_score

score = read_score("program.codetta")
xml = to_musicxml(score)
pages = render_score(score).pages
write_score(score, "score.html")
```

表示APIが受け取る実行可能な入力はScore Modelだけです。MusicXMLを単体で組版する`render_musicxml()`は外部譜面の表示にも使えますが、そのMusicXMLをCodettaプログラムとして実行しません。

## CLI

```powershell
python -m rendering program.codetta -o score.html
python -m rendering program.codetta -o score.svg
python -m rendering program.codetta -o score-debug.html --debug
python -m rendering external.musicxml -o external.html
```

HTMLは生成したSVGを直接埋め込むため、閲覧時のCDNやネット接続は不要です。`Print / Save PDF`からブラウザの印刷機能でPDFへ保存できます。複数ページのSVGは`score.svg`、`score-2.svg`のように書き出します。

## 実装境界

- `rendering/model.py`はScore Modelを表示用の時間軸へ投影する。
- `rendering/musicxml.py`は表示モデルをMusicXML 4.0へ変換する。
- `rendering/renderer.py`はMusicXMLをVerovioへ渡し、SVG / HTMLを生成する。
- PerformerはScore Modelから直接演奏し、レンダリング済みSVGやMusicXMLを読まない。
- MusicXML ImportからScore Modelを復元するAdapterはv0.1の次の実装範囲とする。

## 制約

- 一つのスコア内では同じ拍子を使用する。
- MusicXMLは1,024小節、16,384音符・休符断片までとする。
- 記譜音価は四分音符の1/8、つまり32分音符単位までとする。
- 和音は表示と演奏に対応するが、Codetta v0.1の計算構文としてはエラーにする。
- 深い入れ子はMusicXMLのスラー・括弧番号16個を循環利用するため、表示上の判別には限界がある。

## 検証

テストではMusicXMLの音符、休符、タイ、スラー、括弧、終止線と、通常表示にDebug文字列が混入しないことを検証します。Verovioがインストールされている場合は、実際のSVGに五線、音部記号、拍子、音符、符幹、小節線、タイ、スラー、休符、括弧線が含まれることも確認します。
