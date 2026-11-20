"""FR-1096..FR-1098, NFR-SEC-024: generative AI for HVE Studio — optional and contacted only on an explicit user action.

Providers (INT-003, INT-004):
  azure   / key   : Azure OpenAI (Microsoft Foundry) chat completions with an api-key
  azure   / entra : the same, with a short-lived token from the signed-in Azure CLI; resources listed through ARM
  copilot / gh    : Microsoft Copilot SDK with the GitHub CLI's token passed explicitly (tools disabled)
  copilot / byok  : Microsoft Copilot SDK with a bring-your-own-key provider (tools disabled)

Nothing here runs at import time and nothing is contacted unless a request handler calls it.  Keys and tokens are
held in memory (or the OS vault through secret_store) and are never logged, returned, written to files, put on a
command line or into the environment.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import release
import secret_store

TIMEOUT = 60  # PARAM-068: seconds for one AI response (and for a connection check)
AZURE_API_VERSION = "2024-10-21"          # Azure OpenAI inference (chat completions), GA
ARM = "https://management.azure.com"
ARM_SUBSCRIPTIONS_API = "2022-12-01"
ARM_COGNITIVE_API = "2023-05-01"
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com"
COPILOT_PACKAGE = "microsoft-copilot-sdk"
AUTHS = {"azure": ("key", "entra"), "copilot": ("gh", "byok")}
BYOK_TYPES = ("openai", "azure", "anthropic")
ID_RE = re.compile(r"\b(?:[A-Za-z0-9_.\-]+:)?[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{2,}\b")
RECOMMEND_RE = re.compile(r"RECOMMEND\s+(Q-\d{3,})\s*[:：]\s*([A-Z])\b")
# Kinds of information the AI may receive (AC-530). File paths, code, commit and Issue/PR bodies and secrets never.
SENT_KINDS = ("id", "title", "status", "acceptance-criteria-text", "question-text", "count", "repository-name")
LIST_LIMIT = 150


class AIError(Exception):
    """code: auth-failed | forbidden | not-found | timeout | rate-limited | missing-component | signin-required |
    unsupported-token | no-subscription | bad-config | consent-required | provider-error"""

    def __init__(self, code: str, detail: str = "", action: str = ""):
        super().__init__(detail or code)
        self.code, self.detail, self.action = code, detail, action

    def as_dict(self) -> dict:
        return {"error": self.code, "detail": self.detail, "action": self.action}


# ---------------------------------------------------------------- configuration & keys
def check_config(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        raise AIError("bad-config", "configuration missing")
    provider, auth = cfg.get("provider"), cfg.get("auth")
    if provider not in AUTHS or auth not in AUTHS[provider]:
        raise AIError("bad-config", "unknown provider or authentication method")
    clean = {"provider": provider, "auth": auth}
    for k in ("endpoint", "deployment", "model", "byokType", "subscription", "account"):
        v = cfg.get(k)
        if v is not None:
            clean[k] = str(v).strip()[:500]
    if clean.get("endpoint"):
        clean["endpoint"] = _endpoint(clean["endpoint"])
    return clean


def _endpoint(url: str) -> str:
    p = urllib.parse.urlparse(url)
    local = (p.hostname or "") in ("127.0.0.1", "localhost", "::1")
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise AIError("bad-config", "the endpoint must be an https URL")
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}"


def key_name(provider: str, endpoint: str) -> str:
    return f"ai:{provider}:{(endpoint or '').lower().rstrip('/')}"


class Keys:
    """Per-session keys (memory only) in front of the OS vault."""

    def __init__(self):
        self.lock = threading.Lock()
        self.session: dict[str, str] = {}

    def status(self, provider: str, endpoint: str) -> dict:
        name = key_name(provider, endpoint)
        with self.lock:
            in_session = name in self.session
        stored = secret_store.exists(name) if endpoint else False
        return {"stored": stored, "session": in_session, "vault": secret_store.availability()}

    def put(self, provider: str, endpoint: str, key: str, persist: bool) -> dict:
        if not key or len(key) > 4096:
            raise AIError("bad-config", "key is empty or too long")
        name = key_name(provider, endpoint)
        if persist:
            vault = secret_store.availability()
            if not vault["available"]:
                raise AIError("vault-unavailable", vault["reason"])
            try:
                secret_store.save(name, key)
            except secret_store.StoreError as exc:
                raise AIError("vault-failed", str(exc)) from exc
            with self.lock:
                self.session.pop(name, None)
        else:
            with self.lock:
                self.session[name] = key
        return self.status(provider, endpoint)

    def delete(self, provider: str, endpoint: str) -> dict:
        name = key_name(provider, endpoint)
        with self.lock:
            self.session.pop(name, None)
        if secret_store.availability()["available"]:
            try:
                secret_store.delete(name)
            except secret_store.StoreError as exc:
                raise AIError("vault-failed", str(exc)) from exc
        return self.status(provider, endpoint)

    def get(self, provider: str, endpoint: str) -> str:
        name = key_name(provider, endpoint)
        with self.lock:
            if name in self.session:
                return self.session[name]
        try:
            key = secret_store.load(name)
        except secret_store.StoreError as exc:
            raise AIError("vault-failed", str(exc)) from exc
        if not key:
            raise AIError("auth-failed", "no key is set for this endpoint", "enter the key in the AI settings")
        return key


# ---------------------------------------------------------------- signed-in tools (token taken at run time, in memory)
def _tool(name: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    exe = shutil.which(name)
    if not exe:
        raise AIError("missing-component", f"{name} is not installed",
                      "install the Azure CLI (https://aka.ms/installazurecli)" if name == "az"
                      else "install the GitHub CLI (https://cli.github.com)")
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AIError("timeout", f"{name} did not answer in {timeout} s") from exc
    except OSError as exc:
        raise AIError("missing-component", str(exc)) from exc


def azure_account() -> dict:
    r = _tool("az", ["account", "show", "--output", "json"])
    if r.returncode:
        raise AIError("signin-required", "not signed in to Azure (or the sign-in expired)", "az login")
    data = json.loads(r.stdout or "{}")
    return {"account": (data.get("user") or {}).get("name") or "", "tenant": data.get("tenantId") or ""}


def azure_token(resource: str) -> str:
    r = _tool("az", ["account", "get-access-token", "--resource", resource, "--output", "json"])
    if r.returncode:
        raise AIError("signin-required", "could not get a token from the Azure CLI", "az login")
    token = json.loads(r.stdout or "{}").get("accessToken")
    if not token:
        raise AIError("signin-required", "the Azure CLI returned no token", "az login")
    return token


def github_status() -> dict:
    """AC-545: the GitHub CLI's active account on github.com and where its token comes from."""
    r = _tool("gh", ["auth", "status", "--hostname", "github.com"])
    text = (r.stdout or "") + (r.stderr or "")
    if r.returncode:
        raise AIError("signin-required", "the GitHub CLI is not signed in to github.com", "gh auth login")
    account, source = "", "gh"
    for line in text.splitlines():
        m = re.search(r"Logged in to github\.com (?:account|as) (\S+)\s*\(([^)]*)\)", line)
        if m and (not account or "Active account: true" in text):
            account = account or m.group(1)
            src = m.group(2)
            source = "env" if re.search(r"GH_TOKEN|GITHUB_TOKEN|GH_ENTERPRISE_TOKEN", src) else "gh"
    return {"account": account, "tokenSource": source}


def github_token() -> str:
    r = _tool("gh", ["auth", "token", "--hostname", "github.com"])
    token = (r.stdout or "").strip()
    if r.returncode or not token:
        raise AIError("signin-required", "the GitHub CLI returned no token", "gh auth login")
    if token.startswith("ghp_"):
        raise AIError("unsupported-token", "classic personal access tokens (ghp_) are not supported by the Copilot SDK",
                      "gh auth login (OAuth) or a fine-grained token (github_pat_)")
    return token


def signin(provider: str) -> dict:
    if provider == "azure":
        return {"provider": provider, **azure_account()}
    if provider == "copilot":
        return {"provider": provider, **github_status()}
    raise AIError("bad-config", "unknown provider")


# ---------------------------------------------------------------- HTTP
def _http(method: str, url: str, headers: dict, body: dict | None = None, timeout: float = TIMEOUT) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - https (or loopback) checked by _endpoint
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        code = {401: "auth-failed", 403: "forbidden", 404: "not-found", 429: "rate-limited"}.get(exc.code, "provider-error")
        action = {"forbidden": "assign the Cognitive Services OpenAI User role on the resource",
                  "auth-failed": "check the key or sign in again", "not-found": "check the endpoint and deployment",
                  "rate-limited": "wait and try again"}.get(code, "")
        raise AIError(code, f"HTTP {exc.code} {detail}".strip(), action) from exc
    except TimeoutError as exc:
        raise AIError("timeout", f"no answer in {timeout} s", "try again") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise AIError("timeout", f"no answer in {timeout} s", "try again") from exc
        raise AIError("not-found", f"cannot reach the endpoint ({exc.reason})", "check the endpoint") from exc


def _arm(path: str, token: str) -> list[dict]:
    out, url = [], ARM + path
    while url and len(out) < 1000:
        data = _http("GET", url, {"Authorization": "Bearer " + token}, timeout=30)
        out += data.get("value") or []
        url = data.get("nextLink")
    return out


def list_resources(level: str, subscription: str = "", account: str = "") -> list[dict]:
    """FR-1097: what the signed-in Azure identity can list (subscriptions -> OpenAI/AI Services accounts -> deployments)."""
    token = azure_token(ARM)
    if level == "subscriptions":
        subs = _arm(f"/subscriptions?api-version={ARM_SUBSCRIPTIONS_API}", token)
        return sorted(({"id": s.get("subscriptionId"), "name": s.get("displayName") or s.get("subscriptionId")}
                       for s in subs if s.get("state", "Enabled") == "Enabled"), key=lambda s: s["name"].lower())
    if level == "accounts":
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", subscription or ""):
            raise AIError("bad-config", "choose a subscription")
        accts = _arm(f"/subscriptions/{subscription}/providers/Microsoft.CognitiveServices/accounts"
                     f"?api-version={ARM_COGNITIVE_API}", token)
        return sorted(({"id": a.get("id"), "name": a.get("name"), "location": a.get("location"), "kind": a.get("kind"),
                        "endpoint": (a.get("properties") or {}).get("endpoint", "")}
                       for a in accts if a.get("kind") in ("OpenAI", "AIServices")), key=lambda a: a["name"].lower())
    if level == "deployments":
        if not re.fullmatch(r"/subscriptions/[^?#]+/providers/Microsoft\.CognitiveServices/accounts/[^/?#]+", account or "", re.I):
            raise AIError("bad-config", "choose a resource")
        deps = _arm(f"{account}/deployments?api-version={ARM_COGNITIVE_API}", token)
        return sorted(({"name": d.get("name"), "model": ((d.get("properties") or {}).get("model") or {}).get("name", ""),
                        "version": ((d.get("properties") or {}).get("model") or {}).get("version", "")} for d in deps),
                      key=lambda d: d["name"].lower())
    raise AIError("bad-config", "unknown level")


# ---------------------------------------------------------------- calling a provider
def _azure_chat(cfg: dict, keys: Keys, messages: list[dict], max_tokens: int) -> tuple[str, str]:
    endpoint, deployment = cfg.get("endpoint"), cfg.get("deployment")
    if not endpoint or not deployment:
        raise AIError("bad-config", "endpoint and deployment are required")
    if cfg["auth"] == "key":
        headers = {"api-key": keys.get("azure", endpoint)}
    else:
        headers = {"Authorization": "Bearer " + azure_token(COGNITIVE_SCOPE)}
    url = f"{endpoint}/openai/deployments/{urllib.parse.quote(deployment)}/chat/completions?api-version={AZURE_API_VERSION}"
    data = _http("POST", url, headers, {"messages": messages, "max_tokens": max_tokens})
    choice = (data.get("choices") or [{}])[0]
    return ((choice.get("message") or {}).get("content") or "").strip(), data.get("model") or deployment


def copilot_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("copilot") is not None
    except (ImportError, ValueError):
        return False


def _copilot_chat(cfg: dict, keys: Keys, messages: list[dict]) -> tuple[str, str]:
    if not copilot_available():
        raise AIError("missing-component", f"the Copilot SDK is not installed (Python 3.11+)",
                      f"pip install {COPILOT_PACKAGE}")
    import asyncio
    import tempfile

    from copilot import CopilotClient  # type: ignore[import-not-found]

    try:
        from copilot.rpc import PermissionDecisionReject  # type: ignore[import-not-found]
    except ImportError:  # older SDKs
        PermissionDecisionReject = None  # noqa: N806

    def deny(request, invocation):  # AC-527: never allow a tool (file edit, shell, fetch ...)
        return PermissionDecisionReject(feedback="tools are disabled in HVE Studio") if PermissionDecisionReject else {"kind": "denied"}

    model = cfg.get("model") or ""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    prompt = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
    session_opts: dict = {"tools": {"available_tools": []}, "permissions": {"on_request": deny},
                          "system_message": {"mode": "replace", "content": system}}
    if cfg["auth"] == "byok":
        endpoint = cfg.get("endpoint")
        if not endpoint or not model:
            raise AIError("bad-config", "endpoint and model are required")
        provider = {"name": "byok", "type": cfg.get("byokType") or "openai", "base_url": endpoint,
                    "api_key": keys.get("copilot", endpoint)}
        session_opts.update(github={"capi": {"enabled": False}}, inference={"default_provider": "byok", "providers": [provider]})
        client_opts = {"mode": "empty"}
    else:
        client_opts = {"mode": "empty", "github": {"token": github_token(), "use_logged_in_user": False}}
    if model:
        session_opts["model"] = model

    async def run() -> str:
        with tempfile.TemporaryDirectory(prefix="hve-ai-") as scratch:  # a working directory outside every repository
            async with CopilotClient(**client_opts) as client:
                async with await client.create_session(working_directory=scratch, **session_opts) as session:
                    reply = await asyncio.wait_for(session.send_and_wait(prompt), TIMEOUT)
        data = getattr(reply, "data", None)
        return (getattr(data, "content", None) or (str(reply) if reply is not None else "")).strip()

    try:
        return asyncio.run(run()), model or "copilot"
    except asyncio.TimeoutError as exc:
        raise AIError("timeout", f"no answer in {TIMEOUT} s", "try again") from exc
    except AIError:
        raise
    except Exception as exc:  # the SDK raises many kinds; report the cause without secrets
        text = str(exc)
        code = "auth-failed" if re.search(r"auth|401|token", text, re.I) else "provider-error"
        raise AIError(code, text[:300]) from exc


def chat(cfg: dict, keys: Keys, messages: list[dict], max_tokens: int = 1200) -> tuple[str, str]:
    cfg = check_config(cfg)
    if cfg["provider"] == "azure":
        return _azure_chat(cfg, keys, messages, max_tokens)
    return _copilot_chat(cfg, keys, messages)


def test_connection(cfg: dict, keys: Keys) -> dict:
    started = time.monotonic()
    text, model = chat(cfg, keys, [{"role": "system", "content": "Reply with OK."}, {"role": "user", "content": "ping"}], 5)
    return {"ok": True, "model": model, "ms": int((time.monotonic() - started) * 1000)}


# ---------------------------------------------------------------- what is sent (AC-530) and how answers are checked
def _req_row(r: dict) -> dict:
    return {"id": r["id"], "title": r.get("title") or "", "status": r.get("status") or ""}


def step_context(model: dict, step: int, repo_name: str) -> dict:
    """Only IDs, titles, states, acceptance-criteria text, question text, counts and the repository name."""
    reqs = model.get("reqs") or []
    ctx: dict = {"repository": repo_name, "counts": {"requirements": len(reqs), "goals": len(model.get("goals") or []),
                                                     "testCases": len(model.get("cases") or [])}}
    by_status: dict[str, int] = {}
    for r in reqs:
        by_status[r.get("statusKind") or "unknown"] = by_status.get(r.get("statusKind") or "unknown", 0) + 1
    ctx["counts"]["requirementsByStatus"] = by_status
    cases = model.get("cases") or []
    ctx["counts"]["casesByStatus"] = {s: sum(1 for c in cases if (c.get("status") or "not_run") == s)
                                      for s in sorted({c.get("status") or "not_run" for c in cases})}
    judged = release.judge(model)
    if step == 1:
        ctx["goals"] = [{"id": g["id"], "title": g["title"], "verdict": g["verdict"]} for g in judged["goals"]][:LIST_LIMIT]
        ctx["release"] = {"state": judged["state"], "actionItems": len(judged["items"])}
    elif step == 2:
        ctx["openQuestions"] = [{"id": q["id"], "severity": q.get("severity"), "question": q.get("question"),
                                 "options": q.get("options"), "recommended": q.get("recommend"), "state": q.get("state")}
                                for q in model.get("questions") or [] if not (q.get("state") or "").startswith(release.ANSWERED)][:LIST_LIMIT]
        ctx["notApproved"] = [_req_row(r) for r in reqs if r.get("statusKind") != "approved"][:LIST_LIMIT]
        ctx["stalledCriteria"] = [{"id": a["id"], "requirement": r["id"], "text": a.get("text"), "blockedBy": a.get("blocked")}
                                  for r in reqs for a in r.get("acs", []) if a.get("blocked")][:LIST_LIMIT]
    elif step == 3:
        degree: dict[str, int] = {}
        for e in (model.get("graph") or {}).get("edges", []):
            degree[e["s"]] = degree.get(e["s"], 0) + 1
            degree[e["t"]] = degree.get(e["t"], 0) + 1
        ctx["requirements"] = [{**_req_row(r), "linkedRecords": degree.get(r["id"], 0),
                                "acceptanceCriteria": [{"id": a["id"], "text": a.get("text")} for a in r.get("acs", [])][:6]}
                               for r in reqs if r.get("statusKind") == "approved"][:LIST_LIMIT]
    elif step == 4:
        items = (model.get("implStatus") or {}).get("items") or []
        ctx["implementation"] = [{"id": i["id"], "title": i.get("title"), "state": i.get("state"),
                                  "cases": i.get("cases")} for i in items][:LIST_LIMIT]
    elif step == 5:
        ctx["release"] = {"state": judged["state"], "reasons": [r["code"] for r in judged["reasons"]],
                          "goals": [{"id": g["id"], "title": g["title"], "verdict": g["verdict"], "counts": g["counts"]}
                                    for g in judged["goals"]],
                          "actionItems": [{"kind": i["kind"], "id": i["id"], "title": i["title"]} for i in judged["items"]][:LIST_LIMIT]}
    else:
        features = (model.get("catalog") or {}).get("features") or []
        by_id = {r["id"]: r for r in reqs}
        ctx["catalogMismatches"] = [{"id": f["req"], "catalogTitle": f.get("title"), "catalogStatus": f.get("status"),
                                     "title": by_id[f["req"]].get("title"), "status": by_id[f["req"]].get("status")}
                                    for f in features if f.get("req") in by_id and not f.get("derived")
                                    and (f.get("title") != by_id[f["req"]].get("title")
                                         or f.get("status") != by_id[f["req"]].get("status"))][:LIST_LIMIT]
        ctx["openAudits"] = len([a for a in model.get("audits") or [] if not (a.get("state") or "").startswith(("解消", "対応済み"))])
    return ctx


STEP_NAMES = {1: "Understand the whole picture", 2: "Settle the requirements", 3: "Check the impact",
              4: "Track progress", 5: "Decide on the release", 6: "Tidy up and record"}


def messages_for(step: int, question: str, contexts: list[dict], lang: str) -> list[dict]:
    language = "Japanese" if lang == "ja" else "English"
    system = (
        "You assist a product manager who uses HVE Studio, a read-only viewer of a repository's requirements, "
        f"catalog and test ledger. The current work step is {step} ({STEP_NAMES.get(step, '')}). "
        f"Answer in {language}, concisely, with short paragraphs or bullet lists. "
        "Use only the data in the JSON context; never invent requirement, criterion, question or test IDs. "
        "Cite the IDs you rely on exactly as written in the context (including a 'repo:' prefix when present). "
        "You cannot change data, approve, or run tests; say so if asked. "
        "When you recommend an answer to a question (Q-xxx), choose only among its listed options and add a line "
        "'RECOMMEND Q-xxx: <option letter>' followed by the reason. If no option fits, say that you cannot recommend.")
    data = json.dumps(contexts, ensure_ascii=False, separators=(",", ":"))
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Context (JSON):\n{data}\n\nQuestion:\n{question}"}]


def _options(q: dict) -> set[str]:
    return set(re.findall(r"(?:^|[／/、,\s])([A-Z])\s*[:：]", " " + (q.get("options") or "")))


def check_answer(text: str, known_ids: set[str], questions: dict[str, dict]) -> dict:
    """AC-526: IDs not in the model are flagged; a recommendation outside the question's options is not shown."""
    ids, seen = [], set()
    for m in ID_RE.finditer(text):
        i = m.group(0)
        if i not in seen:
            seen.add(i)
            ids.append({"id": i, "known": i in known_ids})
    recs = []
    for m in RECOMMEND_RE.finditer(text):
        q = questions.get(m.group(1))
        valid = bool(q) and m.group(2) in _options(q)
        recs.append({"question": m.group(1), "option": m.group(2) if valid else None, "valid": valid})
    return {"ids": ids, "recommendations": recs}


def ask(cfg: dict, keys: Keys, step: int, question: str, lang: str, sources: list[tuple[str, dict]]) -> dict:
    """sources: (repository name, model) for every repository the user consented to send."""
    if not question.strip():
        raise AIError("bad-config", "the question is empty")
    if step not in STEP_NAMES:
        raise AIError("bad-config", "unknown step")
    contexts = [step_context(model, step, name) for name, model in sources]
    messages = messages_for(step, question.strip()[:2000], contexts, lang)
    text, model_name = chat(cfg, keys, messages)
    known, questions = set(), {}
    for name, model in sources:
        ids = {n["id"] for n in (model.get("graph") or {}).get("nodes", [])}
        for r in model.get("reqs") or []:
            ids.add(r["id"])
            ids.update(a["id"] for a in r.get("acs", []))
        for q in model.get("questions") or []:
            ids.add(q["id"])
            questions[q["id"]] = q
        ids.update(str(c.get("id")) for c in model.get("cases") or [])
        ids.update(g["id"] for g in model.get("goals") or [])
        known |= ids
        if len(sources) > 1:
            known |= {name + ":" + i for i in ids}
    checked = check_answer(text, known, questions)
    return {"answer": text, "provider": cfg["provider"], "auth": cfg["auth"], "model": model_name,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"), "step": step,
            "sentKinds": list(SENT_KINDS), "sent": contexts, **checked}
