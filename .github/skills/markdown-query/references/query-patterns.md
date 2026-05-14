# クエリ例パターン集

## 1. キーワードでざっくり横断検索
```
python -m hve.mdq search --q "業務要件" --top-k 5
```

## 2. 特定ディレクトリのみ
```
python -m hve.mdq search --q "アーキテクチャ" --paths "users-guide/*" --top-k 3
```

## 3. 完全一致 / 厳密一致したい（grep モード）
```
python -m hve.mdq search --q "Bounded Context" --mode grep --top-k 10
```

## 4. frontmatter タグでフィルタ
```
python -m hve.mdq search --q "API" --tags backend security
```

## 5. snippet を最小化してさらに節約
```
python -m hve.mdq search --q "..." --top-k 3 --max-tokens 300 --snippet-radius 1
```

## 6. 人間可読で確認 → chunk_id を抽出 → 詳細取得
```
python -m hve.mdq search --q "..." --format compact
python -m hve.mdq get --chunk-id <ID>
```

## 7. 見出しレベル別の俯瞰
```
python -m hve.mdq list --paths "docs/*" --heading-level 2
```
