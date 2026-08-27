## タスク（Goal / Context / Source）

### Goal（目的）
以下の「Knowledge 項目」（事業要件文書 D クラスの 1 件）について、Microsoft 365 上に文書内容を補強・修正できる一次情報があるか検索する。

### Context（背景）
本検索結果は、Post-DAG の AKM 検証フェーズで `knowledge/D??-*.md` を事実ベースで更新するための根拠として使われる。**根拠が無い更新は行わない**ため、確証の無い情報は載せず、見つからなかった場合は STATUS: NOT_FOUND を返すこと。

### Source（情報源）
ユーザーがアクセス権を持つ Microsoft 365 データ。公開 Web 情報・一般論・モデルの事前学習知識は使わない。