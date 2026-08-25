import subprocess
import json
import sys

def run_command(args):
    print(f"Running: {' '.join(args)}", file=sys.stderr)
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    return result.returncode, result.stdout, result.stderr

# Run Query 1
q1_args = [
    r".\.venv\Scripts\python.exe", "-m", "mdq", "search",
    "--q", "起動時 precheck 設定 整合性 ブランチ GH_TOKEN Agent セッション 前",
    "--top-k", "8", "--max-tokens", "1800", "--return-unit", "chunk",
    "--paths", "hve-dev/requirement-definition.md"
]
ret1, out1, err1 = run_command(q1_args)

# Run Query 2
q2_args = [
    r".\.venv\Scripts\python.exe", "-m", "mdq", "search",
    "--q", "ベースブランチ GitHub Issue PR GH_TOKEN 起動前 検証",
    "--top-k", "8", "--max-tokens", "1800", "--return-unit", "chunk",
    "--paths", "users-guide/*"
]
ret2, out2, err2 = run_command(q2_args)

# Run Query 3
q3_args = [
    r".\.venv\Scripts\python.exe", "-m", "mdq", "search",
    "--q", "Prompt 追加プロンプト 入力 検証 設定",
    "--top-k", "8", "--max-tokens", "1800", "--return-unit", "chunk",
    "--paths", "hve-dev/requirement-definition.md", "users-guide/*"
]
ret3, out3, err3 = run_command(q3_args)

output_data = {
    "q1": {"exit_code": ret1, "stdout": out1, "stderr": err1},
    "q2": {"exit_code": ret2, "stdout": out2, "stderr": err2},
    "q3": {"exit_code": ret3, "stdout": out3, "stderr": err3}
}

with open("results.json", "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)
print("Done saving to results.json", file=sys.stderr)