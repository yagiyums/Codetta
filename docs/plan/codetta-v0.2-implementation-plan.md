# Codetta v0.2 Implementation Plan

## 1. v0.1から変更が必要な箇所

現在のv0.1には次の制約があります。

- Voiceは小節内の演奏レーンであり、変数として継続するIDや名前を持たない
- AST／IRは算術式のみ
- 各小節が単一式のBlockになる
- Conductorは単一式・単一小節しか生成できない
- Spannerは小節境界を越えられない
- Score Modelにsection、repeat、volta、phrase、Voice groupがない
- ComposerのPython投影は単一の式または`result`代入のみ
- Performerは`Fraction`だけを扱い、楽譜を直線的に一度再生する

主に以下を拡張します。

- `codetta/score_model.py`
- `codetta/serialization.py`
- `codetta/score_parser.py`
- `codetta/ast.py`
- `codetta/ir.py`
- `codetta/semantic_analyzer.py`
- `conductor/`
- `performer/`
- `rendering/`
- `composer/`
- v0.2 exampleとE2Eテスト

v0.1ファイルは既存の意味論で読み続け、v0.2とはバージョン別に解析します。

## 2. Codetta v0.2 Language Specification案

楽譜上の時間位置をプログラム順序とし、以下を正式な対応関係にします。

```text
横方向         sequence / evaluation order
縦方向         relation / application / structured value
Voice          variable / state / data flow
duration       value lifetime
tie            lifetime extension
measure        statement block
section        lexical scope / function
repeat         iteration
volta          conditional branch
rehearsal mark function identifier
```

名前付きVoice上に新しい値領域が始まるとAssignmentになります。水平に並ぶ未グループ化要素を暗黙の加算とはせず、v0.2の加算は明示的なslur内だけで成立させます。

v0.1の楽譜は従来どおり解析し、既存コードの意味を変更しません。

## 3. Voiceと変数の正式な意味論

Voice IDを小節間で継続するシンボルIDに変更し、表示用のVoice名を追加します。

```text
Voice {
    id
    name
    staff
    events
}
```

同じIDのVoiceはsection内で同じ変数を表します。

- 新しい値のonsetでAssignment
- 同時刻の右辺を評価してから左辺を更新
- 次のAssignmentまで、または記譜されたlifetime終了まで値を保持
- tieは値を変えずにlifetimeだけ延長
- section外のVoiceは参照不可
- branch後は選択されたbranchの環境を引き継ぐ
- loop iteratorはrepeat内だけのlocal Voice

直接記譜されたIntでは、v0.2は最初のattack durationから値を導出し、後続tieは値に加算せずlifetimeだけを延長します。v0.1のtie合計による整数解釈はv0.1 Parserに残します。

## 4. repeatとfor / whileの区別

Score Modelに`RepeatRegion`を追加します。

counted repeatは以下のいずれかを持ちます。

- 固定回数
- 回数を供給するInt Voice
- Array Voice。この場合は配列長を回数とする

iterator Voiceには`0`から`count - 1`を順に設定します。

conditional repeatは終端にBool Voiceを持ちます。body終了後に条件を評価し、trueなら先頭へ戻ります。したがってネイティブ表現はpost-test loopです。

通常のpre-test `while`は、先頭にゼロ回実行を可能にするvolta guardを組み合わせて表現します。

内部的には両方を別ノードへ下げます。

```text
For(iterator, source, body)
While(condition, body, test_at_end)
```

無限ループ対策として、標準最大iteration数を10,000回とし、CLIとComposer設定で変更可能にします。

## 5. voltaとif / elseの正式な意味論

`VoltaGroup`と`VoltaEnding`を追加します。

- branch直前まで保持されるBool Voiceがcondition
- 1番括弧がtrue branch
- 2番括弧がfalse branch
- 2番括弧がなければelse無しif
- 選択されなかった括弧は実行しない
- 分岐後は共通の継続位置へ合流
- 両branchで更新される同一Voiceは同じ型でなければならない
- 一方だけで作られる変数は、合流後に無条件参照できない

通常画面では標準的なvolta bracketを表示し、`IF`などの命令文字列は表示しません。

## 6. Arrayの楽譜表現

同一VoiceまたはVoice group上の連続値を`PhraseRegion`で囲みます。

```text
Voice values: 1 ─ 2 ─ 4 ─ 6
              └── phrase ──┘
```

この横方向の順序を`ArrayLiteral`として解釈します。

- 要素型はSemantic Analyzerが統一
- 異なる型の混在はエラー
- 空配列は型推論できる文脈でのみ許可
- Voice group上のphraseはArray of Structになる
- phrase外の値列は通常のAssignment sequence

保存するのは開始・終了anchorと対象Voiceであり、配列要素そのものをJSON命令として保存しません。

## 7. Structの楽譜表現

複数の名前付きVoiceを縦方向の`VoiceGroup`として束ねます。

```text
person
├─ age
├─ height
└─ score
```

同一時刻の各field Voiceの値が`StructLiteral`になります。field名はVoice名から導出します。

Voice groupに横方向のPhraseRegionを設定すると、各時刻の縦方向groupが要素となり、Array of Structになります。

同じfield名の重複、欠落、異なる時刻の不完全なgroupはSemantic Errorにします。

## 8. Function / Call / Returnの楽譜表現

名前付きsectionをFunctionとして扱います。

```text
Section {
    id
    rehearsal_mark
    name
    start_measure
    end_measure
    parameter_voice_ids
    return_voice_ids
}
```

parametersとreturnsはsection境界のVoice portです。これは命令opcodeではなく、sectionに入出力されるVoiceの構造的関係として保存します。

- parameter順序は上から下のVoice順
- section内部Voiceはlexical local
- return Voiceはsection終端のoutput port
- 複数returnは縦groupからStruct／Tupleへ拡張可能
- section外の無名領域をtop-level `main` とする

Function Callは`SectionReference`として記譜します。

- 対象rehearsal mark
- 呼び出し位置
- argument Voice
- result Voice

通常表示ではsection名と参照記号だけを表示し、Debug Modeで引数対応を表示します。

## 9. Floatの表現方法

Floatは特定音高や臨時記号へ割り当てません。

縦方向に積んだ複合スカラーとして表現します。

```text
significand : 314
exponent    : -2
```

これを以下として解釈します。

```text
314 × 10^-2 = 3.14
```

- 上段がsignificand
- 下段がbase-10 exponent
- 数全体の負号は既存のNegate slur
- 通常表示はコンパクトな二段scalar group
- Debug Modeでは`314 × 10⁻² : Float`を表示

ASTでは`FloatLiteral(significand, exponent)`、IRではIEEE 754のFloatへ変換します。v0.1の正確な除算を維持するため、`Rational`は内部数値型として残します。

## 10. 型システム

次の型を持たせます。

```text
Type
├─ Numeric
│  ├─ Int
│  ├─ Rational
│  └─ Float
├─ Bool
├─ Array<T>
├─ Struct{field: Type}
├─ Function<(parameters) -> return>
├─ Tuple
└─ Void
```

主な規則は次のとおりです。

- Boolと数値の暗黙変換は禁止
- Int同士の除算はRational
- Floatを含む数値演算はFloat
- Array要素は同一型
- Structはfield名とfield型で検査
- Array indexはIntのみ
- if／while conditionはBoolのみ
- 同じVoiceへの再代入は型を維持
- Function引数と戻り値は使用箇所から型推論
- 推論不能または矛盾する場合はSemantic Error
- 配列範囲外アクセスはRuntime Error

比較はまず`<`、`>`、`==`を実装し、Boolを生成します。楽譜ではcrescendo、diminuendo、unison系の関係記号から導出し、音高opcodeにはしません。

## 11. AST拡張案

既存の`Integer`、`Sum`、`Product`、`Negate`、`Reciprocal`を残し、以下を追加します。

```text
Literal
├─ Integer
├─ FloatLiteral
└─ BoolLiteral

VariableRef
Assignment
UnaryExpr
BinaryExpr
Comparison

If
For
While

ArrayLiteral
ArrayAccess

StructLiteral
FieldAccess

FunctionDecl
FunctionCall
Return

Block
Program
```

すべてのノードに`SourceRef`を持たせ、Composerの診断を元のevent、region、Voice、sectionへ戻せるようにします。

BoolLiteralはAST上では扱いますが、標準的な楽譜生成では比較結果として構築し、専用音符へ割り当てません。

## 12. IR拡張案

IRでは記譜情報を除去し、解決済みSymbol IDと型を持たせます。

```text
Const
Load
Store

Unary
Binary
Compare

MakeArray
Index
MakeStruct
GetField

Branch
ForLoop
WhileLoop

Call
Return

Function
Program
```

ASTの名前参照はSemantic AnalyzerでSymbol IDへ解決します。PerformerはIRだけを実行し、Score Modelへ直接アクセスしません。

構造化IRを維持し、v0.2初期段階ではCFG／SSAまでは導入しません。

## 13. `.codetta`スキーマ変更案

`format`は引き続き`codetta-score`とし、バージョンを`0.2`へ上げます。

追加する楽譜構造は次のとおりです。

```text
Voice.name
voice_groups
phrases
relations
sections
section_references
repeats
voltas
```

`relations`は次のような音楽的・幾何的情報だけを持ちます。

- connector形状
- input anchor
- output anchor
- 対象Voice
- 時間位置
- nesting

`ArrayAccess`や`ADD`などの命令名は保存しません。Semantic Analyzerが配置、connector、入力型、出力型から意味を導出します。

v0.1ファイルはそのまま読めるようにし、明示的なv0.2保存を行うまで書き換えません。

## 14. Composer変更案

Composerへ以下を追加します。

- Explorer内のSections／Voicesツリー
- Voice作成、名前変更、削除
- Voice group作成とfield編集
- 値およびlifetime配置
- Phrase／Array region編集
- Repeat regionとiterator編集
- Volta branch編集
- Section／parameter／return編集
- Section referenceによるFunction Call作成
- Array index／field relation作成
- v0.2 Python subsetとの同期
- 型・scope・flow診断
- 構造単位のUndo／Redo

現在のようにフロントエンドがJSON全体を直接書き換える方式だけでは複雑な編集を安全に扱えないため、サーバーへ検証付きの構造編集APIを追加します。

通常表示は五線譜中心のままとし、次の情報はDebug Modeだけに表示します。

- inferred type
- variable lifetime
- scope
- branch
- iteration
- function ports
- array／struct region
- data flow

## 15. Performer変更案

Performerに次を追加します。

- typed runtime value
- lexical environment
- Voice／Symbol binding
- scope stack
- call stack
- Assignment
- comparisonとBool
- if／else
- counted repeat
- conditional repeat
- Array／Struct
- ArrayAccess／FieldAccess
- Function Call／Return
- Float演算
- iteration、step、call-depth制限

Playerは単に楽譜を左から右へ一度鳴らすのではなく、実行traceを利用します。

- for／whileでは実行回数分repeat区間を再生
- ifでは選択されたvoltaだけを再生
- Function Callでは参照されたsectionを再生
- 非実行branchは再生しない
- 最大音声時間制限は維持

これにより、E2Eプログラムを評価して`10`を得るだけでなく、実際に通った制御フローを音楽として再生できます。

## 実装順序

1. v0.2仕様テストとバージョン互換層
2. Score Model／`.codetta`スキーマ
3. AST／型検査／IR／Performer
4. Score Parser／Conductorと主要E2E
5. repeat、volta、sectionのMusicXML出力
6. 実行traceに基づく再生
7. Composerの構造編集とPython同期
8. 自己レビュー、全テスト、Windows起動確認
9. `enhancement/v0.2`をコミット・push
