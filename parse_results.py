import json

with open("results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for q_name, q_data in data.items():
    print("=" * 60)
    print(f"QUERY: {q_name}")
    print(f"Exit Code: {q_data['exit_code']}")
    print(f"Stderr: {q_data['stderr'].strip()}")
    print("=" * 60)
    
    stdout = q_data['stdout']
    if not stdout.strip():
        print("No matches")
        continue

    # Parse stdout line-by-line or as full JSON
    lines_parsed = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines_parsed.append(json.loads(line))
        except Exception as e:
            pass
            
    if not lines_parsed:
        # Maybe it was a single JSON array?
        try:
            lines_parsed = json.loads(stdout)
            if not isinstance(lines_parsed, list):
                lines_parsed = [lines_parsed]
        except Exception:
            pass

    print(f"Total results: {len(lines_parsed)}")
    for i, res in enumerate(lines_parsed, start=1):
        if isinstance(res, str):
            print(f"  Result {i} (unparsed string): {res[:200]}")
            continue
        path = res.get("path") or res.get("file_path") or "N/A"
        heading = res.get("heading") or res.get("heading_path") or "N/A"
        lines = res.get("lines") or "N/A"
        text = res.get("text") or res.get("content") or res.get("snippet") or ""
        
        print(f"  Result {i}:")
        print(f"    Path: {path}")
        print(f"    Heading: {heading}")
        print(f"    Lines: {lines}")
        text_lines = text.strip().splitlines()
        preview = "\n".join(text_lines[:5])
        if len(text_lines) > 5:
            preview += f"\n    ... ({len(text_lines)-5} more lines)"
        print(f"    Text Preview:\n{preview}\n")