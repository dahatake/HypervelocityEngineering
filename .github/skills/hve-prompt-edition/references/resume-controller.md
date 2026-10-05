## durable resume controller 境界（FR-PROMPT-11）

この reference は、自然言語の resume 要求時にのみ Prompt Edition root から参照される。
request v1 は変更せず、hash / CAS 手順も root の既存契約と同じである。

自然言語の resume request はこの境界で扱うが、**request v1 は変更しない**。execution ID、
resume action、replay 値などの resume 固有情報を request JSON に追加せず、当該 resume 試行の
一時入力として扱う。

1. Agent は自然言語から対象 execution、action、必要な replay 値を解決する。一意に定まらない
  候補や不足値は利用者へ日本語で確認し、値や秘密情報を推測・捏造しない。
2. 共通 SSOT の `ResumeService.list_candidates()` で候補を取得し、選択後に最初の
  `ResumeService.build_plan()` を呼ぶ。候補、action、risk、missing replay keys、
  `expected_state_version`、`resume_plan_hash` を含む resume plan を日本語で**提示**する。
3. 提示済み resume plan を実行する意思が明確な**明示承認**を得るまで、lease の取得も
  `orchestrate` 子プロセスの起動も行わない。曖昧な同意は承認とみなさず再確認する。
4. 明示承認後、Agent は承認済み hash と当該試行だけの replay 値を既存 `hve resume` へ
  内部転記して委譲する。`hve resume` は `ResumeService.build_plan()` をもう一度呼び、現在の
  durable state と HEAD から plan を**再計算**する。
5. 再計算した `resume_plan_hash` が承認済み hash と一致した場合だけ、`hve resume` が
  `ResumeService.acquire()` を呼ぶ。`acquire()` は plan の `expected_state_version` を用いた
  **CAS** を実施し、成功後だけ既存の `hve resume` / `orchestrate` child 経路へ委譲する。
  Prompt Edition controller 自身は先行または重複して `acquire()` を呼ばない。
6. hash 不一致または CAS 競合で plan が **stale** なら、child / 子プロセスは **0 件**のまま
  起動せず停止する。Agent が最新 plan を再計画して日本語で**再提示**し、利用者から
  **再承認**を得るまで続行しない。
7. 複数 Workflow instance は登録済みの `ordinal` 順に再開し、**最初の失敗**で停止する。
  instance 完了後に構築された後続 `ResumePlan` は別の明示承認の対象とする。Agent は新しいplanを
  再提示し、利用者の再承認を得てから同じhash再計算/CAS手順を繰り返す。先行planのhashを後続planへ流用してはならない。
  後続 instance を暗黙に起動せず、独自の resume 判定や別の実行エンジンを追加しない。
8. output再調停で実行対象が0件になったinstanceは、subcommandなしchildを起動せず、共通
  `ResumeService` が取得済みfenced leaseとoutputを再確認して`succeeded`へ確定する。
9. replay 値は当該planのプロセス内だけで使用し、durable store、request v1、ログへ保存しない。
  instance完了時に平文値を破棄し、後続planへ流用しない。後続planが同じkeyを必要とする場合も
  改めて再入力・再承認する。認証情報などの秘密値が必要な場合も、既存の安全な入力経路を使い、Agent は値を生成しない。

利用者へ**コマンド**、`request path`、`execution hash` または `resume_plan_hash` の入力・転記・
コピーを**求めない**。候補取得、plan の作成、内部引数への転記、既存 CLI の起動は Agent が行う。