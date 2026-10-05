# リポジトリオンボーディング 入出力例

> 本ファイルは `repo-onboarding-fast/SKILL.md` の最小成果物契約と簡潔な例を収容する参照資料です。

---

## 成果物契約

- 出力先は `work/run/<run-id>/<task>/onboarding.md` に固定する。
- 後続Subが再利用できるよう、作業開始に必要な短い事実だけを残す。
- 必須フィールドは「入口」「境界」「参照元/踏襲元」「標準コマンド」「不明点」の5つ。
- 同じ出力先に既存 `onboarding.md` がある場合は、直接編集せず削除→新規作成する。

## 簡潔な出力例

````markdown
# onboarding

## 入口（主要パス）

- `<entry-path>` — `<why-this-is-an-entry>`

## 境界（API/データ/責務）

- `<boundary-name>` — `<contract-or-responsibility>`

## 参照元/踏襲元（類似実装パス）

- `<reference-path>` — `<what-to-follow>`

## 標準コマンド

- `<command>` — `<purpose>`

## 不明点と Spike 案

- `<unknown>` — `<next-check>`
````

## 既存 onboarding.md がある場合

1. `work/run/<run-id>/<task>/onboarding.md` の存在を確認する。
2. 存在する場合は既存ファイルを削除する。
3. 最新の最小事実で新規作成する。
4. 作成後、ファイルが空でないことを確認する。
