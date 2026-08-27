# 入力ファイル名が違うときの Prompt 例（入力別名）

← [スニペット索引](README.md)

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## 入力別名とは

HVE の各 Step は、決められたパス（**canonical**）から入力を読みます。
手元のファイル名がそれと違う場合、**その実行に限って** 読み替えを指示できます。

```text
canonical: docs/catalog/app-catalog.md   ←  HVE が読むと決まっているパス
actual:    inputs/my-app-catalog.md      ←  実際に手元にあるファイル
```

- **ファイルはコピーされません。** 元の場所のまま読まれます。
- **出力先は変わりません。** 成果物のパスも I/O 契約もそのままです。
- **その実行だけの読み替えです。** 設定として保存されません。

---

## 使い方

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の Web 画面設計を進めたい
- Workflow: aad-web
- Step: 1, 2.1
- パラメータ: app_ids=APP-NNN
- 入力: docs/catalog/app-catalog.md は inputs/my-app-catalog.md にあります
- 制約:
  - ファイルをコピーしたり移動したりしないこと
  - 出力先のパスは変更しないこと
- 期待する成果物: docs/catalog/screen-catalog.md、docs/screen/

まず実行計画だけを見せてください。
計画に「入力別名: docs/catalog/app-catalog.md → inputs/my-app-catalog.md」が
表示されることを私が確認します。
私が「実行してください」と書くまで、実行はしないでください。
```

提示される計画には、次の行が表示されます。

```text
- 入力別名: `docs/catalog/app-catalog.md` → `inputs/my-app-catalog.md`
```

この行が出ていなければ、別名は適用されていません。

---

## canonical パスの調べ方

canonical は「選んだ Step が実際に読む入力パス」です。正本は
`hve/workflow_registry.py` の `StepDef.required_input_paths` です。

依頼文の中で「`aad-web` の Step 1 と 2.1 が読む入力パスを教えてください」と聞けば、
Copilot が正本を調べて答えます。自分で確かめたい場合は次のコマンドでも確認できます。

```sh
python -c "from hve.workflow_registry import get_workflow; w=get_workflow('aad-web'); [print(s.id, list(s.required_input_paths or [])) for s in w.steps]"
```

**選んだ Step が読まないパスを canonical に指定すると、実行前に拒否されます。**

---

## v1 で受け付けないもの

| 指定 | 結果 | 理由 |
|---|---|---|
| `docs/dataflow/*.md`（glob） | 拒否 | v1 は glob 別名に非対応 |
| `docs/catalog/screen-catalog-{key}.md`（placeholder） | 拒否 | v1 は placeholder を含む入力に非対応 |
| `docs/catalog/`（ディレクトリ） | 拒否 | v1 はディレクトリ入力に非対応 |
| `C:\work\my-file.md`（絶対パス） | 拒否 | リポジトリ内の相対パスのみ |
| `../outside/my-file.md` | 拒否 | `..` によるリポジトリ外参照は不可 |
| symlink / junction | 拒否 | リポジトリ外を指し得るため |
| 存在しないファイル | 拒否 | 実行前に存在を確認する |
| 同じ canonical に 2 つの別名 | 拒否 | どちらを使うか決まらない |
| 選んだ Step が **生成する** 成果物 | 拒否 | 上流の生成物を差し替えると系譜が壊れる |

拒否された場合、HVE は理由を表示して計画を提示せずに停止します。
**別名を使わずに済ませる（canonical の場所にファイルを置く）** のも有効な選択肢です。

---

## 複数の別名を指定する

```text
- 入力:
  - docs/catalog/app-catalog.md は inputs/my-app-catalog.md にあります
  - docs/catalog/data-model.md は inputs/my-data-model.md にあります
```

それぞれ別の canonical を指す限り、複数指定できます。

---

## 関連

- 制約の実装: `hve/input_aliases.py`
- Workflow 別の単独例: [README.md](README.md) の索引から選んでください
