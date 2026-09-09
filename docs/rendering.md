# 通常の五線譜による表示

## 追加する層

既存の`conductor/score_writer.py`は囲みを持つ実行用SVGを作り、`performer/score_reader.py`はその囲みをIRに復元します。この形式を通常の楽譜SVGに置き換えるだけでは、Performerが必要とする情報が失われます。

新設の`rendering/`に表示専用の経路を置きます。

```text
Codetta IR → rendering/model.py → rendering/musicxml.py → rendering/renderer.py
                                                              ↓ Verovio
MusicXMLファイル ──────────────────────────────────────────────→ SVG / HTML

実行用Codetta SVG → performer/score_reader.py → evaluator / player
```

表示層は評価器・再生器を呼ばず、入力式の計算、定数畳み込み、再生音価への変換をしません。たとえば`1 / 0`も表示できます。五線譜は記譜音価と構造の投影であり、演奏スケジュールではありません。

## IRに不足している情報

| 情報 | 今回の扱い |
|---|---|
| 拍子・小節 | 既定4/4。小節境界で音を分割しタイで結ぶ |
| 調号・異名同音の綴り | 既定ハ長調。調号の五度数を指定でき、負ならフラット系、その他はシャープ系の綴りを選ぶ |
| 音部記号 | 既定ト音記号。ヘ音記号も指定可能 |
| 音符の種類・付点・タイ | 有理数の記譜音価から導出する |
| 声部・五線への配置 | 主フレーズを上、各制御フレーズを追加の五線へ配置する |
| 声部間の空き時間 | 位置合わせの休符を表示モデルにだけ追加する。計算上の数値ではない |
| 和音・通常の休符・複数声部 | 現在の計算IRにはない。表示モデルとMusicXML入力が扱い、IRの演算は拡張しない |
| 改行・改ページ・符幹・記号の衝突回避 | Verovioの組版に任せる |

表示上の開始位置・長さと、計算値は別です。伸縮フレーズの表示幅は主声部と制御声部の長い方に合わせます。入力IRは変更しません。

## レンダラーと出力形式の選択

[VerovioのPython版](https://book.verovio.org/installing-or-building-from-sources/python.html)はWindowsとPython 3.10をサポートし、MusicXMLを読み込んでSVGを出力できます。既存のPythonプロジェクトから直接利用できるため採用します。MusicXMLは[直接インポーター](https://book.verovio.org/toolkit-reference/input-formats.html#musicxml)を指定します。

OpenSheetMusicDisplayはブラウザ内の動的表示を中心にする場合、MuseScoreはデスクトップ編集とPDF出力を中心にする場合の候補です。今回はSVGを先に生成し、同じSVGを自己完結したHTMLに埋め込む構成とします。閲覧時のCDN、サーバー、ネット接続は不要です。PDFはHTMLをブラウザで印刷して保存します。

## Codettaの構造を示す記号

これは表示上の規約であり、通常の音楽理論で各記号が算術演算を意味するわけではありません。

| IR | 通常表示 |
|---|---|
| Span | 同じ高さの音符。分割した音価をタイで結ぶ |
| Sequence | 同じ五線上で横に連結し、複数の音がある範囲をスラーで示す。同種の連続加算は一つのスラーにまとめる |
| Scale | 主声部の上の実線の括弧線と、下の制御用五線 |
| Unscale | 主声部の上の破線の括弧線と、下の制御用五線 |
| Invert | フレーズの下の括弧線 |
| Zero | コーダ記号。記譜上の時間は進めない |
| Emit | 最後の小節の終止線 |

括弧線やスラーの重なる深い入れ子では、通常表示だけでは制御関係を一意に読み取れない場合があります。Debug modeでは各フレーズの位置に演算名やリテラルを注記します。通常表示にはAST、リテラルの数値、演算名、計算結果のラベルを出しません。拍子や小節番号など通常の楽譜に必要な数字は表示対象です。

MusicXMLとレンダリング済みSVG/HTMLは表示・交換用です。今回MusicXMLからCodettaプログラムを復元する機能は追加しません。実行用形式は`--format executable-svg`で明示して生成します。

## APIとCLI

```python
from conductor.compiler import compile_expression
from rendering.model import NotationOptions
from rendering.musicxml import to_musicxml
from rendering.renderer import render_ir, render_musicxml, write_ir

program = compile_expression("(3 + 5) * 2")
xml = to_musicxml(program, NotationOptions(beats=4, beat_type=4, fifths=0))
pages = render_musicxml(xml).pages
write_ir(program, "score.html")
```

`render_ir()`と`render_musicxml()`はページごとのSVG文字列を返します。`write_ir()`のHTML出力には通常表示とDebug modeの切り替えを含めます。表示時のIR注記は、計算を実行して求めた答えではなく、フレーズに対応するノード種別・リテラルです。

```powershell
.\.venv\Scripts\python.exe -m conductor "(3 + 5) * 2" -o score.html
.\.venv\Scripts\python.exe -m conductor "(3 + 5) * 2" -o score.svg
.\.venv\Scripts\python.exe -m conductor "(3 + 5) * 2" -o score.musicxml
.\.venv\Scripts\python.exe -m conductor "(3 + 5) * 2" --debug -o score-debug.svg
.\.venv\Scripts\python.exe -m rendering input.musicxml -o score.html
```

生のMusicXML入力では`score-partwise`形式の`.xml`、`.musicxml`と、単一スコアを含む`.mxl`を受け付けます。IRを持たないMusicXMLにはCodetta用Debug modeを追加しません。入力楽譜にもともとある歌詞や発想標語は通常どおり表示されます。

SVGからは第2ページ以降も`score-2.svg`…として書き出し、HTMLには全ページを含めます。ページ寸法はMusicXML表示CLIの`--page-width`と`--page-height`、またはAPIの`RenderOptions`で指定できます。PDFの直接CLI出力はありません。

## 制約

- MusicXML生成は1,024小節・32五線・16,384音符/休符断片までです。記譜音価は四分音符の1/8（32分音符）単位です。
- MusicXMLへ変換できる音高はMIDI 12〜127です。現行IRの通常出力C4（60）は範囲内です。
- 同時に重なるスラーまたは括弧線は同一五線で各16本までです。深い構造の可読性には限界があります。
- 和音や複数声部は表示モデルとMusicXML入力に対応します。計算言語としての和音の意味は未定義です。
- MusicXMLインポートの対応範囲はVerovioに依存します。MuseScoreとの完全な表示一致、任意の記譜拡張の保存は保証しません。
- 表示用MusicXMLの休符は位置合わせに使い、演奏順序を示すものではありません。制御声部が同時刻に並んでもPerformerでの同時再生を意味しません。

## 検証

通常のテストは標準ライブラリの`unittest`を使い、Verovioがインストールされていれば実際の組版も検証します。小節内の声部ごとの音価、タイ、臨時記号の取り消し、和音、複数声部、複数ページ、デバッグ表示の分離、既存の実行経路を確認します。

生成したMusicXMLを正式なXSDで検証するには、`requirements-dev.txt`をインストールし、[W3C MusicXML 4.0のschemaディレクトリ](https://github.com/w3c/musicxml/tree/v4.0/schema)から`musicxml.xsd`、`xml.xsd`、`xlink.xsd`を同じローカルディレクトリに保存してください。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:CODETTA_MUSICXML_SCHEMA = 'C:\path\to\musicxml-schema'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

XSD検証時はネット接続せず、このディレクトリのスキーマだけを使います。環境変数を設定しなければXSD検証の1件はスキップされます。
