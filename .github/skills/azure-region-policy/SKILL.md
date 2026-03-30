---
name: azure-region-policy
description: "Azure リソース作成時のリージョン優先順位ポリシー。Japan East を既定とし、フォールバック順序・SWA 例外・理由記録義務を規定する。Deploy Agent がリージョン選択する際に参照する。"
---

# azure-region-policy

## 目的

Azure リソース作成時の **リージョン優先順位** を一元管理する。
各 Deploy Agent は本 Skill を参照し、リージョン選択の判断根拠とする。

本 Skill は以下のパターンを統合して提供する:
- **P-01**: Azure Region Policy / フォールバック

---

## 1. 標準リージョン優先順位

Azure リソース作成時のリージョンは、以下の優先順位で選択する:

| 優先順位 | リージョン | 備考 |
|---------|-----------|------|
| 1（既定） | **Japan East** | 第一候補。特に理由がない限りこのリージョンを使用する |
| 2 | Japan West | Japan East が利用不可の場合 |
| 3 | East Asia | Japan West も利用不可の場合 |
| 4 | Southeast Asia | 上記すべてが利用不可の場合 |

---

## 2. SWA（Static Web Apps）例外

Azure Static Web Apps は **Japan East に非対応** のため、以下の専用優先順位を使用する:

| 優先順位 | リージョン | 備考 |
|---------|-----------|------|
| 1（既定） | **East Asia** | SWA の第一候補 |
| 2 | Japan West | East Asia が利用不可の場合 |
| 3 | Southeast Asia | 上記すべてが利用不可の場合 |

> **注意**: Japan East は SWA で使用できないため、SWA リソース作成時は必ず本例外ルールに従うこと。

---

## 3. 理由記録義務

既定リージョン（§1 の Japan East、§2 の East Asia）以外を使用する場合は、以下を `work-status` に記録する:

- 使用したリージョン名
- 理由（例: 機能非対応 / クォータ上限 / リソース種別固有の制約）
- 確認日時

### 3.1 記録例

```markdown
- 2026-03-30: リージョン Japan West を使用（理由: Japan East でクォータ上限に到達。az vm list-usage で確認済み）
```

---

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-01 の詳細
- `work/Issue-skills-migration-investigation/migration-matrix.md` — DEFER-2 評価
