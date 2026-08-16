#!/usr/bin/env python3
"""OpenAI 互換エンドポイントが VS Code の BYOK で使えるかを検証する。

VS Code の Chat / Agent が必要とする機能を、実際にリクエストして確認する。

    python verify_endpoint.py --url http://127.0.0.1:11434 --model qwen3:8b
    python verify_endpoint.py --url http://127.0.0.1:39839 --model qwen3-8b-cuda-gpu:2

チェック内容:
    1. モデル一覧            GET  /v1/models
    2. チャット補完          POST /v1/chat/completions
    3. ストリーミング        POST /v1/chat/completions (stream=true)
    4. tool calling         POST /v1/chat/completions (tools=[...])
       -> Agent モードで使うには、構造化された tool_calls が返り、
          arguments が指定どおりであることが必要。
     5. 実効 context（任意） GET /api/ps (--expected-context 指定時)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

OK, NG, WARN = "[  OK  ]", "[FAILED]", "[ WARN ]"

# タイムアウトは「このモデルは使えない」とは別の事象であり、同じ判定にしてはならない。
_timed_out = False
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(url: str, body: dict | None = None, timeout: int = 600) -> tuple[int, str]:
    global _timed_out
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with _no_proxy_opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", errors="replace") or "")
    except TimeoutError as e:
        _timed_out = True
        return -1, f"TimeoutError: {e}"
    except Exception as e:  # noqa: BLE001
        if isinstance(getattr(e, "reason", None), TimeoutError):
            _timed_out = True
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    p = argparse.ArgumentParser(description="BYOK エンドポイントの検証")
    p.add_argument("--url", required=True, help="例 http://127.0.0.1:11434")
    p.add_argument("--model", required=True, help="/v1/models が返す id をそのまま指定する")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument(
        "--require-agent",
        action="store_true",
        help="tool calling の arguments 不備を失敗として扱う",
    )
    p.add_argument(
        "--expected-context",
        type=int,
        help="Ollama /api/ps の実効 context_length に期待する正の整数",
    )
    args = p.parse_args()
    if args.expected_context is not None and args.expected_context < 1:
        p.error("--expected-context は正の整数で指定してください")

    base = args.url.rstrip("/")
    failures = 0
    warnings = 0

    print(f"エンドポイント: {base}")
    print(f"モデル        : {args.model}")
    print()

    # 1. モデル一覧
    status, body = request(f"{base}/v1/models", timeout=args.timeout)
    if status == 200:
        try:
            ids = [m["id"] for m in json.loads(body).get("data", [])]
        except Exception:  # noqa: BLE001
            ids = []
        print(f"{OK} 1. モデル一覧 (GET /v1/models)")
        print(f"        利用可能: {ids}")
        if args.model not in ids:
            print(f"{WARN}    指定した model '{args.model}' が一覧にありません。")
            print("        Foundry Local では `foundry cache list -o json` の id を使います。")
            warnings += 1
    else:
        print(f"{NG} 1. モデル一覧 (GET /v1/models) -> {status}")
        print(f"        {body[:200]}")
        failures += 1

    # 2. チャット補完
    status, body = request(f"{base}/v1/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "「OK」とだけ返してください。"}],
        "max_tokens": 64, "temperature": 0, "stream": False,
    }, timeout=args.timeout)
    if status == 200:
        print(f"{OK} 2. チャット補完")
    else:
        print(f"{NG} 2. チャット補完 -> {status}")
        print(f"        {body[:300]}")
        if "not loaded" in body:
            print("        Foundry Local はモデルをロードしないと 400 になります:")
            print("          foundry model load <alias>")
        failures += 1

    # 3. ストリーミング
    status, body = request(f"{base}/v1/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "1から3まで数えて"}],
        "max_tokens": 32, "temperature": 0, "stream": True,
    }, timeout=args.timeout)
    if status == 200 and body.lstrip().startswith("data:"):
        print(f"{OK} 3. ストリーミング (SSE)")
    elif status == 200:
        print(f"{WARN} 3. ストリーミング: 200 だが SSE 形式ではありません")
        warnings += 1
    else:
        print(f"{NG} 3. ストリーミング -> {status}")
        failures += 1

    # 4. tool calling
    status, body = request(f"{base}/v1/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "What is the weather in Tokyo? Use the tool."}],
        "tools": [TOOL], "max_tokens": 512, "temperature": 0, "stream": False,
    }, timeout=args.timeout)

    if status != 200:
        print(f"{NG} 4. tool calling -> {status}")
        print(f"        {body[:300]}")
        failures += 1
    else:
        try:
            msg = json.loads(body)["choices"][0]["message"]
        except Exception as e:  # noqa: BLE001
            print(f"{NG} 4. tool calling: 応答を解析できません ({e})")
            failures += 1
        else:
            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not tool_calls:
                print(f"{NG} 4. tool calling: 構造化された tool_calls が返りませんでした")
                if "tool_call" in content:
                    print("        モデルは本文にツール呼び出しを書いていますが、")
                    print("        ランタイムが構造化フィールドへ変換していません。")
                    print("        -> このモデル/ランタイムの組み合わせでは Agent モードは使えません。")
                failures += 1
            else:
                fn = (tool_calls[0].get("function") or {})
                raw_args = fn.get("arguments")
                try:
                    parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:  # noqa: BLE001
                    parsed = None
                # 追加のキーがあっても誤りとは限らないため city の値だけを見る。
                city = parsed.get("city") if isinstance(parsed, dict) else None
                if isinstance(city, str) and city.strip().lower() == "tokyo":
                    print(f"{OK} 4. tool calling（arguments も正しい）")
                else:
                    marker = NG if args.require_agent else WARN
                    print(f"{marker} 4. tool calling: 呼び出しは返るが arguments が期待と異なります")
                    print('        期待: city が "Tokyo" であること')
                    print(f"        実際: {parsed}")
                    print("        -> Agent モードで誤った引数を渡す可能性があります。")
                    if args.require_agent:
                        failures += 1
                    else:
                        warnings += 1

    # 5. Ollama の実効 context（明示時のみ）
    if args.expected_context is not None:
        status, body = request(f"{base}/api/ps", timeout=args.timeout)
        if status != 200:
            print(f"{NG} 5. 実効 context (GET /api/ps) -> {status}")
            print(f"        {body[:300]}")
            failures += 1
        else:
            try:
                running_models = json.loads(body).get("models", [])
                contexts = [
                    item.get("context_length")
                    for item in running_models
                    if item.get("name") == args.model or item.get("model") == args.model
                ]
            except Exception as e:  # noqa: BLE001
                print(f"{NG} 5. 実効 context: 応答を解析できません ({e})")
                failures += 1
            else:
                if args.expected_context in contexts:
                    print(f"{OK} 5. 実効 context = {args.expected_context}")
                else:
                    actual = contexts if contexts else "指定モデルが /api/ps にありません"
                    print(f"{NG} 5. 実効 context が期待値と一致しません")
                    print(f"        期待: {args.expected_context}")
                    print(f"        実際: {actual}")
                    failures += 1

    print()
    if _timed_out:
        print("注意: タイムアウトのため、モデル適合性はこの実行結果から判断できません。")
        print("      他のジョブが同じサーバーを使っていないか確認し、")
        print(f"      --timeout （現在 {args.timeout} 秒）を伸ばして再実行してください。")
        print("      検証処理としては失敗のため、終了コード 1 を返します。")
        print()
    if failures:
        print(f"結果: 失敗 {failures} 件 / 警告 {warnings} 件")
        if not _timed_out:
            print("VS Code の BYOK でこの組み合わせを使うのは推奨できません。")
        return 1
    if warnings:
        print(f"結果: 失敗 0 件 / 警告 {warnings} 件")
        print("Chat では使えますが、Agent モードでは問題が起きる可能性があります。")
        return 0
    print("結果: すべて OK。Chat / Agent の両方で使えます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
