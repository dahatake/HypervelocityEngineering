## 対象: knowledge/ の要求定義文書

`knowledge/business-requirement-document-status.md` で Unknown または Tentative の項目を優先して、`knowledge/` の D01〜D21 の文書を、出典で確かめた事実で補ってください。

- D 文書は hve_knowledge_write で全文を書いてください。knowledge-management Skill の構成（メタデータ 6 項目、§1〜§8）に従い、20,000 文字以内にしてください。この構成を満たさない文書は書き込まれません。
- 既存の内容と他のジョブの変更は残してください。更新の前に hve_read_file で読み、返された SHA-256 を base_sha256 に渡してください。新規作成のときは base_sha256 を null にしてください。
- 調べた不明点と結論は、hve_qa_create で質問票を作り、hve_qa_answer で記録してください。
