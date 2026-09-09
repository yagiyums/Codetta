# Codetta

Codetta is a visual programming language whose source syntax is conventional musical notation.

Codettaは、**通常の五線譜そのものを構文として使うビジュアルプログラミング言語**です。ユーザーは音符、音価、タイ、休符、横方向の時間、縦方向の声部、スラー、括弧線、小節などを編集してプログラムを書きます。

CodettaはMusicXMLを独自解釈する仕組みではありません。Composer上に表示される五線譜が、Scratchのブロックに相当する標準視覚構文です。

`.codetta`は五線譜の構造を保存する正式なファイル形式です。v0.1ではJSONを使用しますが、JSON自体をユーザー向けのソース構文とはみなしません。

```text
五線譜        = Codettaの標準視覚構文
.codetta      = 五線譜構造のシリアライズ形式
Specification = 五線譜をプログラムとして読む規則
Performer     = Specificationに従う実行環境
MusicXML      = 外部楽譜ソフトとの交換形式
```

## 開発状況

`develop`ブランチにはCodetta v0.1の実行系とローカルWeb IDEのComposerを実装しています。

- 正式なCodetta Score Modelと`.codetta` JSON Serialization
- Score ModelからASTを導出するScore Parser / Semantic Analyzer
- 四則演算をScore Modelへ変換するConductor
- `.codetta`だけを入力として正確な有理数計算を行うPerformer
- Score Modelの複数声部を同時再生するWAV / Windows Player
- Score ModelからMusicXMLを生成するExporter
- Verovioによる通常五線譜のSVG / HTMLレンダリング
- 五線譜、Python、`.codetta` JSONを同期するComposer
- `(3 + 5) * 2`を16として実行・表示・再生するcalculator example

旧実行用SVGと旧IRの互換経路は削除し、Score Model中心の構成へ統一しました。MusicXML Importは今後の実装範囲です。

## Codetta全体の役割

### Codetta

五線譜上の時間、同時性、声部、音価、タイ、休符、小節、グルーピングへ計算可能な意味を与える言語仕様です。

### Composer

Codetta標準GUIエディタ / IDEです。左側の五線譜と右側のPythonを同期し、ユーザーはどちらからでもプログラムを編集できます。右側はPythonの代わりに`.codetta` JSONへ切り替えられます。AST、IR、解析結果は通常画面に表示しません。

### Conductor

数式や通常のコードなど、別の表現からCodetta Score Modelへ変換するコンパイラです。出力はScore Modelまたは`.codetta`です。

### Performer

`.codetta`を読み、Score ModelをAST / IRへ変換して実行します。同じScore Modelを通常の楽譜として演奏します。

### MusicXML Adapter

Codetta Score ModelとMusicXMLを相互変換します。MusicXMLは外部楽譜ソフトとのImport / Exportにだけ使用し、Codetta本体のソース形式や実行形式にはしません。

## 基本アーキテクチャ

```text
Composer ─────────┐
                  ↓
Conductor ─→ Codetta Score Model ─→ .codetta
                  ↓                    ↓
                  └──────← deserialize ┘
                           ↓
                Parser / Semantic Analyzer
                           ↓
                         AST / IR
                           ↓
                        Performer

Codetta Score Model ↔ MusicXML Adapter ↔ MuseScore等
Codetta Score Model → Score Renderer → Composerの五線譜
Codetta Score Model ↔ Python Projection → ComposerのPythonペイン
Codetta Score Model ↔ JSON Serialization → ComposerのJSONペイン
```

Score Modelを唯一の**確定済みドキュメント状態**とします。五線譜、Python、JSONの各ペインはScore Modelの異なる投影です。レンダリング済みSVG、MusicXML、AST、IRをComposerの確定状態にはしません。編集中でまだ検証に成功していないPythonまたはJSONだけは、各テキストエディタの一時Draftとして保持します。

## Codetta v0.1 Language Specification

v0.1では整数、四則演算、グルーピング、評価順序、最終結果だけを扱います。除算の中間値と結果は正確な有理数です。浮動小数点による丸めは行いません。

Codetta v0.1では、楽譜を二種類の合成として読みます。

| 楽譜の構造 | プログラム上の意味 |
|---|---|
| 同一声部内の横方向の連結 | 加算と左から右の評価順序 |
| 括弧線でまとめた複数声部 | 乗算と上から下の評価順序 |
| 親グループ内の破線フレーズ | 親の合成演算に対する逆操作 |
| タイで結ばれた同音高の音符 | 一つの値の持続 |
| 音価 | 正整数の大きさ |
| 休符 | 値の不在。レイアウト上の時間だけを占める |
| 実線スラー | 横方向の部分式のグルーピング |
| 小節 | 一つの評価ブロック |
| 小節線 | ブロック境界 |
| 終止線 | 最終結果の確定 |

`C4 = ADD`や`D4 = SUB`のような対応は定義しません。演算は単独の音符ではなく、音符同士の時間関係、同時性、声部、グループ構造から生じます。

## 1. 数値

一つの正整数リテラルは、同じ音高をタイで結んだ一連の音符です。四分音符を1単位とし、タイチェーンの音価の合計を整数値とします。

```text
value(chain) = chainの総音価 / 四分音符の音価
```

| 記譜 | 値 |
|---|---:|
| 四分音符 | 1 |
| 二分音符 | 2 |
| 付点二分音符 | 3 |
| 全音符 | 4 |
| 全音符と四分音符をタイで接続 | 5 |

数値チェーンは次の条件を満たさなければなりません。

- 一つ以上の有音程音符からなる。
- 複数音符の場合、同じ声部と音高で時間的に連続する。
- 複数音符をすべてタイで接続する。
- 音価の合計が四分音符の整数倍になる。
- 小節線を越えない。
- 休符や和音をチェーン内に含めない。

タイで接続されていない音符は別々の数値です。付点二分音符1個と、二分音符の後に四分音符を置いたものは、どちらも評価結果が3になり得ますが、前者は`Integer(3)`、後者は`Add(Integer(2), Integer(1))`です。

### ゼロ

休符は「値がない」ことを表します。休符だけで構成される空の横フレーズを加法単位元0とします。

```text
H() = 0
```

これにより、特定の休符を直接「整数0」に割り当てずにゼロを表現できます。

### 負数

負数は音符自体の属性にはしません。加算の中で破線フレーズに囲まれた値を、加法逆元として読みます。

```text
H(inverse(3)) = -3
```

### 音高

音高はv0.1では整数の大きさや演算子を決定しません。タイで持続する同一音の識別、声部や値の聴き分け、旋律・和声表現に使用します。

将来、型、変数、パターン、データ参照などへ音高や音程関係を使用できるよう、v0.1で固定的な命令コードを割り当てません。

## 2. 横方向：加算と減算

同じ声部・同じ横グループ内の式を、開始位置の早い順に加算します。

```text
H(e1, e2, ..., en) = value(e1) + value(e2) + ... + value(en)
```

評価順序は左から右です。

```text
[3拍] [5拍]  →  3 + 5
```

横グループ内の子を破線フレーズで囲むと、その子の加法逆元になります。

```text
[3拍] [破線で囲んだ5拍]  →  3 + (-5)  →  3 - 5
```

破線記号を単独の`SUB`命令としては扱いません。横方向の加算グループ内にあるため、加法逆元として解釈されます。

## 3. 縦方向：乗算と除算

複数の声部を同じ時間範囲に配置し、通常の括弧線でまとめると垂直グループになります。

```text
P(e1, e2, ..., en) = value(e1) × value(e2) × ... × value(en)
```

計算上の評価順序は上の声部から下の声部です。音楽としては通常の楽譜と同様に同時再生します。

短い声部の残り時間は休符で埋めます。休符はグループの時間範囲を保ちますが、声部の計算値には加算されません。

垂直グループ内の子を破線フレーズで囲むと、その子の乗法逆元になります。

```text
P(8, inverse(2)) = 8 × (1 / 2) = 4
```

除算は独立した音符命令ではなく、垂直構造内の逆元として表現されます。0の乗法逆元は実行エラーです。

## 4. グルーピングと評価順序

Codettaのグループは、通常の楽譜に表示できるスパナーを使用します。

| 記譜 | 構造 |
|---|---|
| 実線スラー | 一つの声部内の横方向グループ |
| 実線括弧 | 複数声部にまたがる垂直グループ |
| 破線スラー・破線括弧 | 親の合成演算に対する逆元 |
| スパナーの入れ子 | 部分式の入れ子 |

グループ範囲は、完全に分離しているか、一方が他方を完全に含む必要があります。意味が曖昧になる交差スパナーは構文エラーです。

評価順序は次のとおりです。

1. 内側のグループを先に評価する。
2. 横グループは左から右へ評価する。
3. 垂直グループは上の声部から下の声部へ評価する。
4. 小節を左から右へ評価する。
5. 最後の小節の値をプログラム結果として出力する。

純粋な四則演算では乗算の順序による値の違いはありませんが、将来の関数呼び出しや副作用に備えて順序を仕様化します。

## 5. 小節、和音、声部

v0.1では一つの小節を一つの評価ブロックとします。

- 小節線で式の評価を確定する。
- 複数小節は左から右へ実行する。
- 最後の小節の値を最終結果とする。
- 最終小節の終止線を出力位置とする。
- 数値リテラルを構成するタイは小節線を越えない。

変数や状態はまだないため、前の小節の値を次の小節から参照する機能はv0.1に含めません。

Score Model、Composer、MusicXML Adapter、Renderer、Playerは和音と複数声部を扱います。複数声部はv0.1の乗算と除算に使用します。

和音はScore Modelへ保存し、通常の和音として表示・演奏できます。ただし、和音を計算上の値としてどう解釈するかはv0.1では未定義です。意味解析中に和音が式として現れた場合はエラーにします。将来のtuple、複数値、複数引数に予約します。

## 6. ASTと形式意味論

Score Parserは五線譜から次のASTを構築します。

```text
Program(blocks)
Block(expression)

Integer(value, source_ref)
Sum(terms)
Product(factors)
Negate(body)
Reciprocal(body)
```

`source_ref`は元の音符、タイ、スラー、括弧、小節を参照します。エラー表示、Debug Mode、実行中のハイライトに使用します。

値関数`V`を次のように定義します。

```text
V(Integer(n))    = n
V(Sum(xs))       = Σ V(x)
V(Product(xs))   = Π V(x)
V(Negate(x))     = -V(x)
V(Reciprocal(x)) = 1 / V(x)    if V(x) != 0
```

`Reciprocal(0)`はゼロ除算エラーです。

`(3 + 5) * 2`のASTは次の形です。

```text
Program
└─ Block
   └─ Product
      ├─ Sum
      │  ├─ Integer(3)
      │  └─ Integer(5)
      └─ Integer(2)
```

実行用IRは楽譜の音高や位置を持たない計算構造にします。

```text
Emit
└─ Multiply
   ├─ Add
   │  ├─ Constant(3)
   │  └─ Constant(5)
   └─ Constant(2)
```

音高、開始位置、音価、声部などの音楽情報はScore Modelに残し、IRへ複製しません。

## Codetta Score Model

Score Modelは、Composerが編集し、`.codetta`が保存する正式なソースモデルです。ASTや計算結果ではなく、五線譜構造を保持します。

```text
Score
├── metadata
├── parts
│   └── staves
│       └── measures
│           ├── time signature
│           ├── key signature
│           ├── clef
│           └── voices
│               └── events
│                   ├── Note
│                   ├── Rest
│                   └── Chord
└── spanners
    ├── Tie
    ├── Slur
    └── Bracket
```

主なモデルは次のとおりです。

```text
Score
  format_version
  language_version
  metadata
  parts[]
  spanners[]

Measure
  id
  number
  time_signature
  key_signature
  duration
  voices[]

Voice
  id
  staff
  events[]

Note
  id
  start
  duration
  pitch
  accidental
  stem

Rest
  id
  start
  duration

Chord
  id
  start
  duration
  pitches[]

Spanner
  id
  type: tie | slur | bracket
  line_style: solid | dashed
  start_anchor
  end_anchor
  staff_range
  voice_range
  nesting_level
```

`start`と`duration`は浮動小数点ではなく有理数で保持します。`nesting_level`は同じ範囲を囲む複数のスラーや括弧の内外関係と描画位置を保持します。IDはタイやスパナーの参照、Composerの選択、Undo / Redoに使用し、通常画面には表示しません。

## `.codetta`保存形式

v0.1ではUTF-8 JSONを使用します。将来、音源やサムネイルなどを同梱する必要が生じた場合はZIPコンテナへ移行できます。

概略例：

```json
{
  "format": "codetta-score",
  "format_version": "0.1",
  "language_version": "0.1",
  "score": {
    "metadata": {
      "title": "Codetta example"
    },
    "parts": [
      {
        "id": "part-1",
        "staves": [
          {
            "id": "staff-1",
            "measures": [
              {
                "id": "measure-1",
                "number": 1,
                "time_signature": {"beats": 8, "beat_type": 4},
                "key_signature": {"fifths": 0},
                "clef": {"sign": "G", "line": 2},
                "barline": "light-heavy",
                "voices": [
                  {
                    "id": "voice-1",
                    "staff": 1,
                    "events": [
                      {
                        "type": "note",
                        "id": "note-1",
                        "start": {"n": 0, "d": 1},
                        "duration": {"n": 3, "d": 4},
                        "pitch": {"step": "C", "alter": 0, "octave": 4}
                      },
                      {
                        "type": "note",
                        "id": "note-2",
                        "start": {"n": 3, "d": 4},
                        "duration": {"n": 1, "d": 4},
                        "pitch": {"step": "D", "alter": 0, "octave": 4}
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ],
    "spanners": [
      {
        "type": "slur",
        "id": "group-1",
        "line_style": "solid",
        "start_anchor": "note-1",
        "end_anchor": "note-2",
        "staff_range": [1, 1],
        "voice_range": [1, 1],
        "nesting_level": 0
      }
    ]
  }
}
```

時刻と音価は全音符を1とする有理数です。四分音符は`{"n": 1, "d": 4}`、付点二分音符は`{"n": 3, "d": 4}`です。

`.codetta`には以下のような解析済みの意味を保存しません。

```json
{
  "meaning": "integer",
  "value": 3,
  "operation": "multiply",
  "result": 16
}
```

値と演算は、保存された音価、タイ、時間的位置、声部、スパナーからLanguage Specificationに従って導出します。

Serialization層ではJSONスキーマ、バージョン、ID、参照、イベントの時刻範囲と重複、タイの連続性、スパナーの範囲、小節長を検証します。

## Score Parser / Semantic Analyzer

```text
.codetta
  ↓ deserialize
Score Model
  ↓ notation validation
Validated Score
  ↓ score parser
Codetta AST
  ↓ semantic analysis
Checked AST
  ↓ lowering
Execution IR
  ↓ evaluator
Result
```

Score Parserは次を行います。

1. タイを解決して数値チェーンを作る。
2. 総音価を四分音符単位の整数へ変換する。
3. 休符を計算対象から除外する。
4. スラーから横方向グループを作る。
5. 括弧線と声部範囲から垂直グループを作る。
6. 破線グループを親の軸に応じて`Negate`または`Reciprocal`へ変換する。
7. 小節ごとに`Block`を作る。
8. 最後の小節へ`Emit`を設定する。

構造が曖昧な場合は推測して実行せず、元の小節、音符、スパナーを示す診断を返します。

## Performer

Performerには二つの独立した入力経路を持たせます。

- 計算：AST / IRを評価する。
- 演奏：Score Modelの音符を楽譜どおり再生する。

演奏データをIRから再構築しません。縦に配置された声部は音楽として同時に鳴ります。計算時には仕様化された順序で上から下へ評価します。

AST / IRの`source_ref`を使い、実行中のノードに対応する五線譜上の音符やグループをハイライトできます。

```powershell
python -m performer examples\calculator\program.codetta --no-play
python -m performer examples\calculator\program.codetta --no-play --wav performance.wav
```

Playerは各音符の開始位置をScore Modelから直接読みます。同じ開始位置の声部は楽譜どおり同時に鳴ります。

## Composer

ComposerはCodettaの標準ソースコードエディタです。PythonからローカルWebアプリとして起動します。引数を省略するとcalculator exampleを開き、`.codetta`ファイルを指定するとそのファイルから開始します。

```powershell
python -m composer
python -m composer examples\calculator\program.codetta
```

### ワークスペース

Composerは分割画面を基本とします。

```text
┌──────────────────────────────┬──────────────────────────────┐
│ Codetta Score                │ Source                       │
│                              │ [Python] [.codetta JSON]     │
│ 通常の五線譜エディタ         │                              │
│ 音符、声部、小節、スラー     │ result = (3 + 5) * 2         │
│                              │                              │
├──────────────────────────────┴──────────────────────────────┤
│ Synced · Codetta v0.1 · result: 16                          │
└─────────────────────────────────────────────────────────────┘
```

- 左ペインは常にCodettaの標準視覚構文である五線譜を表示する。
- 右ペインは`Python`と`.codetta JSON`を切り替える。
- 初期表示はPythonとし、ペイン幅を変更できる。
- 右ペインを閉じてもScore Modelと同期状態は維持する。
- 通常の実行結果はステータス領域に表示し、楽譜内に値ラベルを追加しない。

五線譜の主な編集操作は次のとおりです。

- 音符と休符の挿入
- 音価と音高の変更
- 臨時記号の設定
- タイの接続と解除
- 和音への音符追加
- 声部の追加と切り替え
- 小節の追加と削除
- 実線スラーによる横グループ化
- 破線スラーによる逆操作
- 括弧線による複数声部のグループ化
- 再生と停止
- `.codetta`の保存と読込
- Undo / Redo

### 三つの編集表現

| 表現 | 役割 | Score Modelとの関係 |
|---|---|---|
| Codetta Score | ユーザー向けの標準視覚構文 | 完全な楽譜構造を編集する |
| Python | 計算上の意味を読み書きしやすく表した投影 | ASTを介するため、音高や細かなレイアウトは表せない |
| `.codetta` JSON | 保存形式の構造化ビュー | Score Model全体を損失なく表す |

PythonペインはCodettaに代わる正式なソース形式ではありません。Conductorによる意味的な投影です。例えば、意味を変えずに音高だけを変更した場合、JSONは更新されますがPythonは変化しません。Python側で式を変更した場合は、既存の対応箇所の音高、声部、記譜上の設定を可能な限り保ちながらScore Modelを再構成します。

### 双方向同期

編集のたびに反対側を即座に書き換えず、最後の入力から標準400 msが経過した時点で同期を開始します。待ち時間はComposerの設定で変更できます。

```text
五線譜の編集
  ↓ Score Command
Candidate Score Model
  ↓ validate / semantic analyze
Committed Score Model
  ├─→ render → 左ペイン
  ├─→ AST → Python emitter → Pythonペイン
  └─→ serialize → JSONペイン

Pythonの編集
  ↓ parse supported Python subset
Candidate AST
  ↓ reconcile / score layout
Candidate Score Model
  ↓ validate / semantic analyze / atomic commit
Committed Score Model

JSONの編集
  ↓ parse / schema validation / deserialize
Candidate Score Model
  ↓ notation validation / semantic analyze / atomic commit
Committed Score Model
```

同期は次の規則に従います。

1. 入力中と検証中は入力元のペインを上書きしない。確定後に正規化する場合も、Revision IDが最新であることを確認し、カーソルと選択範囲を復元する。
2. 構文、スキーマ、記譜、意味のすべての検証に成功した場合だけ、Candidateを一回のトランザクションとして確定する。
3. 検証に失敗したDraftは入力元に残し、エラー位置と理由を表示する。左ペインと他の右ペインは最後の正常なScore Modelを表示し続ける。
4. 各編集にRevision IDを付け、遅れて完了した古い変換結果を破棄する。
5. `Editing`、`Checking`、`Synced`、`Invalid`、`Stale`の状態をステータス領域に表示する。
6. Invalid Draftがある間に別のペインで確定済みScore Modelが変わった場合、そのDraftを`Stale`とし、ユーザーが適用し直すか破棄するまで自動確定しない。
7. PythonとJSONを切り替える際は、最後に確定したScore Modelから選択先を生成する。未確定Draftはモードごとに保持する。

これにより、例えばPythonで開き括弧だけを入力した途中状態によって、正しい五線譜が消えることはありません。

### Python Projection v0.1

Pythonペインは次の安全な部分集合だけを受け付けます。

- 整数リテラル
- 二項演算`+`、`-`、`*`、`/`
- 単項マイナス
- 括弧
- 一つの式、またはその式を`result`へ代入する文
- コメントと空行。ただしScore Modelには保存しない
- 正確な有理数を表すためにComposer自身が生成した`fractions.Fraction`のImportと呼び出し

Import、関数呼び出し、属性参照、添字、比較、条件式、ループ、内包表記などは、上記の`Fraction`形式を除いて拒否します。Pythonは`ast`モジュールで構文木として解析し、`eval`や`exec`では実行しません。

除算を含まない例では、次の簡潔なPythonを表示できます。

```python
result = (3 + 5) * 2
```

除算を含む場合、Pythonとして実行してもCodettaと同じ正確な有理数になるよう、正規化後は`Fraction`を使用します。

```python
from fractions import Fraction

result = (Fraction(3) + Fraction(1)) / Fraction(2)
```

ユーザーが`result = (3 + 1) / 2`と入力することも許可し、Codettaへは同じASTとして取り込みます。同期後のPythonは上記の正規形に整形されます。v0.1ではコメント、空白、余分な括弧などPython固有の表記をScore Modelへ保存しないため、次に同期した際に正規化されることがあります。

### Pythonから楽譜への再構成

Pythonは音高、声部配置、符幹方向などを持たないため、ASTと既存Score Modelの対応を使って次の順に楽譜を再構成します。

1. 変更されていないAST部分木は、元の音符ID、音高、声部、スパナーを維持する。
2. 数値だけが変わった場合は、元の音高を保ち、タイを含む音価チェーンを新しい値へ調整する。
3. 演算構造だけが変わった場合は、再利用できる子ノードの記譜を保ち、必要な声部とグループ記号を組み直す。
4. 新しい部分式はConductorの標準レイアウト規則で配置する。
5. 対応を一意に決められない大きな変更では、式全体を標準レイアウトし直す。

自動配置によって音楽的な見た目が変わり得る場合は、確定前のプレビューと`Notation will be relaid out`という診断を表示します。JSONペインからの編集は完全な楽譜構造を含むため、この意味上の不足はありません。

### Undo / Redo

確定した同期は入力元にかかわらず、一つのScore Modelトランザクションとして共通のUndo / Redo履歴へ積みます。未確定のPythonおよびJSON Draftでは、テキストエディタ固有のUndo / Redoを使います。

### Normal Mode

左ペインには通常の五線譜、右ペインには初期状態でPythonを表示します。`.codetta` JSONはユーザーが明示的に切り替えた場合だけ表示します。MusicXML、AST、IR、解析結果は表示しません。JSON内の内部IDは構造上必要なためJSONモードでは表示しますが、五線譜上には重ねません。

### Debug Mode

Semantic Analyzerが生成した次の情報を別レイヤーとして重ねます。

- 音価から導出した整数
- `Sum`と`Product`の範囲
- `Negate`と`Reciprocal`
- 評価順序とデータフロー
- 構文・意味エラー
- 現在実行中のノード

Debug情報は`.codetta`へ保存せず、Score Modelから毎回再生成します。

### 安全性と性能

- Python Draftを任意コードとして実行しない。
- JSONは最大サイズ、ネスト深度、配列長を制限してから解析する。
- 同期変換はUIスレッドの外で実行し、Revision IDでキャンセル可能にする。
- 自動同期だけではファイル保存を行わない。保存操作でのみ`.codetta`へ書き込む。

## Conductor

Conductorは通常の数式や将来のテキスト言語からScore Modelを生成します。

```text
通常の数式
  ↓ text parser
Text AST
  ↓ score layout
Codetta Score Model
  ↓ serialization
.codetta
```

定数畳み込みは行いません。`(3 + 5) * 2`を`16`の音価へ置き換えず、加算、グルーピング、乗算を五線譜上に保存します。

ConductorとComposerが作ったScore Modelは、同じScore ParserとSemantic Analyzerで検証します。

```powershell
python -m conductor "(3 + 5) * 2" -o program.codetta
python -m conductor "(3 + 5) * 2" -o score.musicxml
python -m conductor "(3 + 5) * 2" -o score.html
```

## MusicXMLとの境界

MusicXMLは外部交換形式です。

```text
Score Model → MusicXML Exporter → MusicXML
MusicXML → MusicXML Importer → Score Model  （今後実装）
```

PerformerはMusicXMLを直接実行しません。MusicXMLをCodettaとして利用する場合は、必ずScore ModelへImportして意味解析します。

音符、休符、和音、音高、音価、臨時記号、声部、五線、小節、拍子、調号、音部記号、タイ、実線・破線のスラーと括弧、終止線をImport / Export対象とします。

現在のv0.1実装はScore ModelからMusicXMLへのExportに対応します。Import実装後も、一般の楽曲がCodettaプログラムとして有効とは限りません。Import後にSemantic Analyzerで検証し、無効な箇所をComposer上に表示します。

MuseScoreなどの外部ソフトが声部番号、タイ、破線、スパナー範囲を変更した場合はCodettaとしての意味も変わる可能性があります。

> Codetta MusicXML Profileに含まれる標準記号が維持された場合、`.codetta → MusicXML → .codetta`で得られるASTの意味が一致する。

ファイルのバイト単位の一致や、Codettaと無関係なMusicXMLメタデータの完全保存は保証しません。

## `(3 + 5) * 2`の標準表現

最初のE2E例は1小節の8/4拍子で表します。

上段には付点二分音符の3と、全音符・四分音符をタイで接続した5を置き、実線スラーでまとめます。下段には二分音符の2と、残り6拍を埋める休符を置きます。上下の声部を8拍の実線括弧でグループ化し、最後を終止線にします。

```text
8/4

上声部  | 3拍          5拍                         |
        | 付点二分音符  全音符 〜 四分音符         |
        | └────── 実線スラー ──────┘               |
        |                                           | 実線括弧
下声部  | 2拍          6拍分の休符                 |
        | 二分音符                                  ||
```

Score Parserは次のASTを作ります。

```text
Product
├── Sum
│  ├── Integer(3)
│  └── Integer(5)
└── Integer(2)
```

Performerは16を出力します。音楽としては8拍で、上下の声部を同時に再生します。

## v0.1実装ディレクトリ

```text
codetta/
├── score_model.py
├── serialization.py
├── score_parser.py
├── semantic_analyzer.py
├── ast.py
├── ir.py
└── semantics.py

conductor/
├── parser.py
├── compiler.py
├── score_builder.py
└── score_writer.py

performer/
├── score_reader.py
├── evaluator.py
├── player.py
└── runtime.py

rendering/
├── model.py
├── musicxml.py
└── renderer.py

composer/
├── projection.py
├── server.py
└── static/

examples/
├── calculator/
└── notation/

tests/
```

表示層はScore Modelだけを受け取り、評価器を呼びません。各層は相互の内部実装へ依存せず、Score ModelとAST / IRの公開境界を介して接続します。

## E2E実装状況

- [x] 数式`(3 + 5) * 2`をScore Modelへ変換する。
- [x] 楽譜構造だけを`.codetta`へ保存し、再読込する。
- [x] Score Parserが音価、タイ、声部、スラー、括弧からASTを生成する。
- [x] Performerが正確な有理数で四則演算し、16を出力する。
- [x] Score Modelの音符を同時声部を含めてWAVまたはWindows音声へ出力する。
- [x] MusicXMLへExportする。
- [x] Verovioで通常の五線譜をSVG / HTMLへ描画する。
- [x] 通常表示から値、演算名、AST、IRを除き、Debug表示だけへ重ねる。
- [x] Composerで五線譜、Python、JSONを双方向編集する。
- [ ] MusicXMLをScore ModelへImportする。

自動テストでは、`.codetta`内に`integer`、`multiply`、計算済みの`16`などが保存されていないことも確認します。音価、タイ、声部、スパナーを変更した場合に、その視覚的変更からASTと結果が変わることを検証します。

## v0.1を実行する

Python 3.10以上を使用します。通常五線譜を描画する場合はVerovioをインストールします。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rendering.txt
```

calculator exampleは、`.codetta`、MusicXML、SVG、HTML、WAVを生成し、保存した`.codetta`を再読込して16を出力します。

Composerを起動する場合：

Windowsでは、clone後にリポジトリ直下の`Codetta Composer.cmd`をダブルクリックするとブラウザで起動できます。初回起動時はPython 3.10以上を検出し、`.venv`の作成と依存パッケージのインストールを自動で行います。起動中は表示されたウィンドウを開いたままにし、終了時はそのウィンドウを閉じます。

コマンドラインから起動する場合：

```powershell
.\.venv\Scripts\python.exe -m composer
```

ブラウザでは五線譜とPythonを並べて編集でき、`.codetta` JSONへの切り替え、400 ms後の検証付き同期、音符の音高・臨時記号・符幹編集、Undo / Redo、Debug表示、再生、ファイルの読込・ダウンロード保存を利用できます。

```powershell
.\.venv\Scripts\python.exe examples\calculator\demo.py
```

各段階を別々に実行する場合：

```powershell
python -m conductor "(3 + 5) * 2" -o program.codetta
python -m performer program.codetta --no-play
python -m performer program.codetta --no-play --wav performance.wav
python -m rendering program.codetta -o score.html
python -m conductor "(3 + 5) * 2" -o score.musicxml
```

テスト：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## License

MIT License
