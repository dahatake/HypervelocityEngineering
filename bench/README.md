# conductor と Spec Kit の比較ベンチマーク

同じ課題を、conductor と GitHub Spec Kit（v1.1.1）に解かせて、結果を比べます。
結果は [RESULTS.md](RESULTS.md) にあります。記録がないうちは「未計測」と書かれます。

## 目的

「人の介入 1 回あたり、いくつの要求を検証済みにできたか」を、2 つのツールで比べます。
LLM の実行は、人が手で行います。このフォルダには、課題・隠しテスト・採点と集計の道具があります。

## 構成

| パス | 内容 | ツールに見せるか |
|---|---|---|
| `tasks/<id>/task.md` | 課題の文章と、固定の公開インターフェース | 見せる |
| `tasks/<id>/seed/` | 既存コード（T3 だけ） | 見せる |
| `tasks/<id>/hidden/` | 隠し受入テストと `requirements.json` | **見せない** |
| `tasks/<id>/reference/` | 隠しテストの自己検証用の解答 | **見せない。コピーしない** |
| `bench.py` | 準備・採点・記録・集計 | - |
| `results/` | 実行記録（JSON） | - |
| `RESULTS.md` | 集計ページ（自動生成） | - |

## 課題

| ID | 種類 | 内容 |
|---|---|---|
| T1 | 新規・明確 | 予約と在庫アラートつきの在庫管理（`inventory`） |
| T2 | 新規・曖昧な点あり | 申請の下書き保存と再開（`drafts`）。決まっていない点は、聞かなかった場合の既定が task.md に書いてあり、隠しテストはその既定を確かめる |
| T3 | 既存コードあり | 文書ストア（`docstore`）にロール別の権限を足す。既存の動作の回帰テストを含む |

## 公平にするための条件

- 初期状態は同じ。`bench.py prepare` で作った新しいリポジトリから始める。
- モデルは同じ。バージョンを記録する。
- Copilot のプランは同じ。
- Spec Kit は `--integration copilot`。
- ツールと課題の組み合わせごとに、3 回ずつ実行する（run 1〜3）。毎回、新しいリポジトリから始める。
- 隠しテストは、ツールに見せない。コピーするのは `task.md` と `seed/` だけ（`prepare` が行う）。
- `reference/` と `hidden/` は、ツールのリポジトリにも、エージェントが読める場所にも置かない。
- 作業用のリポジトリは、このリポジトリの外に作る。

## 手順

### 共通（準備）

```powershell
python bench/bench.py selfcheck
python bench/bench.py prepare --task T1 --dest C:\bench\conductor-T1-r1
```

`selfcheck` は、reference が隠しテストにすべて通ることを確かめます。

### conductor

1. 準備したリポジトリへ、toolkit を入れる。
   `python tools/install.py --target C:\bench\conductor-T1-r1`
2. そのリポジトリを VS Code で開く。
3. `/build` を実行し、`TASK.md` の内容を `<request>` として渡す。これが介入 1 回目。
4. conductor が質問したら答える。答えは 1 回ずつ数える。
5. conductor が完了を報告したら、時刻を記録して終える。

### Spec Kit

1. 準備したリポジトリで、Spec Kit を入れる。
   `uv tool install specify-cli`
   `specify init . --integration copilot`
2. エージェントで、次の順に実行する。`TASK.md` の内容は `/speckit-specify` に渡す。
   `/speckit-constitution` → `/speckit-specify` → （必要なら `/speckit-clarify`）→ `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` → `/speckit-converge`
3. `/speckit-converge` が「Converged」と言うまで、`/speckit-implement` と `/speckit-converge` を繰り返す。
4. 呼び出しと手動の指示は、1 回ずつ数える。

### 実行のあいだに記録するもの

| 項目 | 記録の方法 |
|---|---|
| interventions | 送った依頼を数える。最初の依頼が 1 |
| lead_time_min | 最初の依頼から最終状態までの実時間 |
| human_minutes | 人が手を動かした時間（自己申告） |
| credits | AI クレジットまたはプレミアムリクエスト（分かれば） |
| completed_without_correction | 修正の指示を出さずに完了したか |

## 記録と採点

```powershell
python bench/bench.py score --task T1 --repo C:\bench\conductor-T1-r1
python bench/bench.py record --tool conductor --task T1 --run 1 --repo C:\bench\conductor-T1-r1 `
  --interventions 2 --lead-time-min 35 --human-minutes 6 --credits 12 `
  --model <モデル名> --completed-without-correction yes --notes "メモ"
python bench/bench.py record --tool speckit --task T1 --run 1 --repo C:\bench\speckit-T1-r1 `
  --interventions 8 --lead-time-min 50 --tool-version 1.1.1 --completed-without-correction no
```

`score` は、隠しテストを一時フォルダへコピーし、成果物のリポジトリを `PYTHONPATH` に置いて pytest を実行します。
`record` は採点して、`results/<tool>-<task>-r<run>.json` を書きます。conductor の版は `scripts/ebaklib.py` から読みます。

## 指標の定義

| 指標 | 意味 |
|---|---|
| interventions | 人がエージェントに送った依頼の回数。最初の依頼を 1 とし、追加の指示・回答・修正・「続けて」を 1 回ずつ数える。Spec Kit は `/speckit-*` の呼び出しと手動の指示を 1 回ずつ数える |
| hidden_pass / hidden_total | 隠し受入テストを、成果物のリポジトリに対して実行した結果 |
| verified_requirements | 隠しテストがすべて通った要求（R1..Rn）の数。対応は `hidden/requirements.json` |
| NSM | verified_requirements ÷ interventions。人の介入 1 回あたりの検証済み要求数 |
| lead_time_min | 最初の依頼から最終状態までの実時間（分） |
| human_minutes | 人が実際に手を動かした時間（自己申告、分） |
| credits | AI クレジットまたはプレミアムリクエスト数（任意。なければ省く） |
| completed_without_correction | 人が修正の指示を出さずに、ツールが完了を報告したか（yes / no） |

## 仮説

| ID | 仮説 |
|---|---|
| H1 | conductor は、介入回数と人手の時間が少ない |
| H2 | conductor の隠しテスト合格率は、Spec Kit 以上 |
| H3 | conductor はクレジットが多くても、検証済み要求あたり +20% 以内 |
| H4 | 差は、既存コードのある T3 で広がる |

`aggregate` は、両ツールの記録がそろった仮説に「支持」か「不支持」を付けます。そろっていないものは「未検証」です。

## 公開する

```powershell
python bench/bench.py aggregate
git add bench/results bench/RESULTS.md
git commit -m "bench: 結果を更新"
```

実行数が少ないうちは、傾向の参考にとどめ、数を明記して公開してください。
