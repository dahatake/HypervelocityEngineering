---
name: svg-renderer
description: >
  図やダイアグラムをSVGコードとして生成し、画面にレンダリング表示するスキル。 USE FOR: SVG render, SVG draw, SVG diagram creation. DO NOT USE FOR: Mermaid diagrams. WHEN: SVGでレンダリングして、SVGで図を描いて。
metadata:
  origin: user
  version: 2.0.0
---

# SVG ダイアグラム レンダリング スキル

ユーザーの要求に基づき、高品質で見やすいSVG図を作成してください。

## 動作条件

ユーザーが **「SVGでレンダリングして」「SVGで描いて」「SVGで作成して」** など、明示的にSVGでの図の生成を指示した場合に動作します。

### 出力モード（デフォルト: 画面表示モード）

| モード | トリガーキーワード | 動作 |
|---|---|---|
| **🖥️ 画面表示モード（デフォルト）** | レンダリング、表示、描画、図式化、可視化、描いて、render, display, show, visualize, draw | SVG保存 **＋ 画面にレンダリング表示（必須）** |
| **💾 ファイル保存モード** | 作成して（表示指示なし）、保存、ダウンロード、エクスポート、create, save, export | SVG保存 ＋ ファイルパス報告のみ |

> ⚠️ **「レンダリング」「表示」「描画」「図式化」「可視化」のいずれかが含まれる場合、いかなる状況でもファイル保存モードにしてはならない**（強制ルール）。

---

## 手順

**ステップ1: 要件の把握** — 図の種類（フローチャート/シーケンス図/アーキテクチャ図/ER図等）・含める要素・スタイル要件を読み取る。

**ステップ1.5: 出力モードの判定【必須】** — 上記テーブルのトリガーキーワードに基づき判定。キーワードが曖昧な場合は画面表示モードを選択。

**ステップ2: SVGの生成** — 詳細ルール（基本構造・デザインガイドライン・図の種類別ガイドライン）は `references/svg-design-guidelines.md` を参照。

**ステップ3: ファイルの保存** — `.svg` ファイルとして保存し、ファイルパスを報告する。画面表示モードの場合は必ずステップ4に進む。

**ステップ4: 画面へのレンダリング表示【画面表示モード時は必須・スキップ禁止】** — `playwright-browser_navigate` + `playwright-browser_take_screenshot` で表示。詳細は `references/svg-design-guidelines.md` を参照。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/svg-design-guidelines.md` | ステップ2のSVG基本構造・デザインガイドライン・図の種類別ガイドライン、ステップ3〜4のファイル保存・レンダリング詳細手順、品質チェックリスト、強制ルール4つ |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `docs-output-format` | 代替 | Mermaid図を使う場合は docs-output-format §2 の Mermaid 記法指針を参照 |
| `work-artifacts-layout` | 出力先 | SVGファイルの保存先パス |
| `large-output-chunking` | 関連 | 巨大なSVGファイルの分割管理 |
