---
name: large-output-chunking
description: "AGENTS.mdの巨大出力ルール（50k/20k、index+part）を具体的に適用する。大量生成・長文出力・巨大差分になりそうなときに使う。"
---

# large-output-chunking

## 手順（安全に出す）
1) 分割軸を決める（章/サービス/API/モジュール等）
2) AGENTS.md の閾値に従って分割し、artifacts/ に保存
- `artifacts/<name>.index.md`
- `artifacts/<name>.part-0001.md` …
3) index には必ず書く
- 目的 / 参照元（根拠）/ 分割の軸 / 結合順 / 再生成条件（簡単でよい）

## part の先頭に付ける最小メタ
- source（参照元）
- scope（このpartの範囲）
- generated-at（日付だけでよい）
