# HVE GUI Translations

`hve` GUI オーケストレーターの多言語化リソース。

- **ソース言語**: 日本語 (`ja_JP`)。コード中の `self.tr("...")` の引数は日本語のまま。
- **翻訳対象**: 英語 (`en_US`) のみ。

## ファイル

| ファイル | 役割 | Git 管理 |
|---|---|---|
| `translations.pro` | 翻訳抽出対象ソースの単一の情報源 | ✅ |
| `hve_gui_en_US.ts` | 英訳ソース (XML) | ✅ |
| `hve_gui_en_US.qm` | 実行時ロードされるバイナリ | ✅ |

## 更新ワークフロー

PySide6 同梱の `pyside6-lupdate` / `pyside6-lrelease` を使用する。追加 install は不要。

### 1. ソースから翻訳可能文字列を抽出（`.ts` 更新）

`pyside6-lupdate` は `.pro` の直接渡しを廃止したため、`translations.pro` の `SOURCES` を
展開して渡す。`translations.pro` は引き続き対象ソースの単一の情報源とする。

```pwsh
cd hve/gui/i18n
$srcs = [regex]::Matches((Get-Content translations.pro -Raw), '(?m)\.\.[^\s\\]+\.py') |
    ForEach-Object { $_.Value }
pyside6-lupdate @srcs -ts hve_gui_en_US.ts
```

新規 `self.tr("...")` 呼び出しが `hve_gui_en_US.ts` に追加される。既存翻訳はマージされる。

### 2. `.ts` を編集（英訳投入）

エディタまたは Qt Linguist で開き、`<translation>` 要素に英訳を記入する。英訳を入れたら
`type="unfinished"` 属性を削除する（残したままだと未完了扱いになる）。

### 3. `.qm` 生成（実行時用バイナリ）

```pwsh
pyside6-lrelease hve_gui_en_US.ts -qm hve_gui_en_US.qm
```

`hve_gui_en_US.qm` が生成される。**実行時はこのファイルがロードされる**ため、`.ts` 編集後は必ず `.qm` を再生成すること。

## 言語切替

優先順位（高 → 低）:

1. 環境変数 `HVE_GUI_LANG` (`ja_JP` / `en_US` / `auto`)
2. 設定ファイル `hve/.settings.txt` の `[options].language`
3. OS ロケール (`QLocale.system().name()`)
4. フォールバック = `en_US`

設定 UI（[設定] メニュー）で変更可能。変更後はアプリ再起動が必要。

## 新規 GUI 文字列を追加する開発者向け

1. Python 側で `self.tr("日本語文字列")` または `QCoreApplication.translate("Context", "日本語文字列")` でラップする。
2. 新規ファイルの場合は `translations.pro` の `SOURCES` へ追加する。
3. 上記の `pyside6-lupdate` を実行して `.ts` を更新。
4. `.ts` に英訳を追加し、`type="unfinished"` を削除。
5. `pyside6-lrelease` を実行して `.qm` を再生成。
6. 上記 4 ファイル (`.ts`/`.qm` + 該当 .py + `translations.pro`) を同一コミットに含める。
