[日本語](04-customization.md) | **English**

# 4. Configuration and customization

All settings live in one file, `scripts/ebak.config.json`. When you update with the installer, the values you set are kept and only new keys are added.

```json
{
  "management_files": { "requirements": "docs/requirements-definition.md", "catalog": "docs/catalog.md", "...": "..." },
  "base_branch": "main",
  "work": { "dir": "work" },
  "checks": { "profile": "lite", "lite_checks": ["CHK-01", "CHK-02", "CHK-03", "CHK-05", "CHK-09", "CHK-12", "CHK-17", "CHK-19", "CHK-24"] },
  "system_test": { "jobs": "auto", "batch_pytest": true, "budget": { "max_active_cases": 100, "...": "..." } },
  "verify": { "timeout_sec": 1800, "commands": [] },
  "extensions": { "checks": [] }
}
```

Keys you omit take the defaults from `DEFAULT_CONFIG` in `scripts/ebaklib.py`. Keys starting with `_note` are explanations and do not affect behavior.

## 4.1 Context you want on every request

EABK Lite has no hooks and does not add a preamble automatically. If you want a standing preamble, put it in your own Copilot instructions (outside the `AGENTS.md` block, or in your per-user instructions).

## 4.2 Management-data paths (`management_files`)

| Key | Default | Content |
|---|---|---|
| `requirements` | `docs/requirements-definition.md` | Requirements definition (the source of truth) |
| `requirements_dir` | `docs/requirements` | Where a split requirements definition lives |
| `catalog` | `docs/catalog.md` | Catalog |
| `id_registry` | `docs/id-registry.md` | ID registry (written only by `next-id.py`) |
| `ledger` | `tests/system/ledger.json` | System Test ledger (written only by `ledger.py`) |
| `manual_tests` | `docs/manual-tests.md` | Record of manual tests |
| `integrations` | `docs/integrations.md` | External integration catalog |

You can change these to match your directory layout. After changing them, run `python scripts/verify.py --docs-only` to confirm that the checks can read the new paths.

## 4.3 Base branch and work folder (`base_branch` / `work`)

| Key | Default | Meaning |
|---|---|---|
| `base_branch` | `main` | The branch that diff checks (CHK-12 and others) compare against. rd-auditor's diff audit also uses the diff with this branch |
| `work.dir` | `work` | Where temporary files go (logs, evidence, results, audit results). Not tracked by git. EABK Lite does not delete `/work` automatically; delete it by hand when you no longer need it |

## 4.4 Check scope (`checks`)

| Key | Default | Meaning |
|---|---|---|
| `profile` | `lite` | `lite` reports only the CHKs in `lite_checks`. `full` reports all CHKs from CHK-00 to CHK-34 |
| `lite_checks` | `CHK-01, CHK-02, CHK-03, CHK-05, CHK-09, CHK-12, CHK-17, CHK-19, CHK-24` | The CHKs reported in lite: structure and traceability (IDs, references, links between ACs and tests) |
| `ambiguous_words` | 適切, 迅速, 直感的, and so on | List of ambiguous words (CHK-13, full only) |
| `unit_pattern` | A regular expression for seconds, counts, %, and so on | Pattern treated as a hard-coded number and unit (CHK-14, full only) |
| `id_scan_exclude` | `docs/**`, `scripts/**`, `EABK-Studio/**`, and so on | Paths excluded when searching code for requirement IDs (CHK-17, CHK-19) |
| `test_path_pattern` | `tests/`, `*.test.*`, and so on | Paths treated as test code (CHK-09) |
| `temp_file_pattern` | `*.log`, `test-results/`, and so on | Temporary files that must not be committed (CHK-23) |

- In lite, CHKs not in `lite_checks` affect neither the output nor the exit code. To report more CHKs, add their IDs to `lite_checks`. The list is not merged with the default; what you write replaces it.
- To change the scope for one run, pass `--profile lite|full`, for example `python scripts/verify.py --profile full` (the same for `rdcheck.py check`). The option takes precedence over the setting. `profile=lite` in the summary line shows which scope was used.
- The profile applies the same way to `rdcheck.py check`, `verify.py`, and `rdfix.py` (including `--full`). `rdfix.py --full` passes exactly when `verify.py --docs-only` passes with the same profile (the mechanical repairs themselves run regardless of the profile).
- Format warnings (CHK-13 ambiguous words, CHK-14 hard-coded numbers, CHK-15 prohibited synonyms, and so on) exist only in full. Look at them at milestone audits, or whenever you want, with `python scripts/verify.py --docs-only --profile full --show-warnings` ([6.2](06-quality-gates.en.md#62-check-profiles-lite-and-full)).

## 4.5 Running System Tests (`system_test`)

| Key | Default | Meaning |
|---|---|---|
| `jobs` | `auto` | Number of cases `ledger.py run` runs at the same time (`N` or `auto`; auto is CPU count ÷ 4, between 2 and 6). Use it only with cases that share no ports or data |
| `serial_patterns` | `["default_port"]` | Cases whose command contains this string run alone after the parallel run finishes. Adding `"serial": true` to a case does the same |
| `batch_pytest` | `true` | Cases that point to the same pytest file run in one pytest process. Only failed cases are re-run alone. `ledger.py run --no-batch` also turns this off |
| `budget` | `max_active_cases: 100`, and so on | Limits checked by `ledger.py cost --check` (active cases, cases per requirement, seconds per case and in total). Exceeding them exits 1 |

## 4.6 Build, static analysis, and test commands (`verify.commands`)

After the management-data checks, `scripts/verify.py` runs the commands registered here in order. If any one fails, it exits 1. The CI workflow `ebak-verify` runs the same commands.

```json
"verify": {
  "timeout_sec": 1800,
  "commands": [
    { "name": "install", "run": "npm ci", "cache_files": ["package.json", "package-lock.json"] },
    { "name": "build", "run": "npm run build" },
    { "name": "lint", "run": "npm run lint", "parallel": true },
    { "name": "unit", "run": "npm test -- --run", "parallel": true },
    { "name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true, "timeout_sec": 900 }
  ]
}
```

| Key | Meaning |
|---|---|
| `name` | Display name. Also used for the log file name |
| `run` | Shell command run at the repository root |
| `slow` | Commands with `true` are skipped by `verify.py --quick`. Use it for quick local checks (CI does not pass `--quick`, so they run there) |
| `parallel` | Consecutive commands with `parallel: true` run at the same time (lint, type checks, unit tests, and so on). Do not set it on steps that need an earlier step (build) |
| `timeout_sec` | Timeout for this command (defaults to `verify.timeout_sec`) |
| `cache_files` | If these files have not changed since the last success, the command is skipped (for dependency installation; disable with `--no-cache`) |

- Environment-caused failures that match `verify.retry_on` (a regular expression; vitest `Timeout calling`, `ECONNRESET`, and so on) are retried once automatically. To stop this, set `verify.retry_flaky: false`.
- You can also write plain strings, such as `"commands": ["python -m pytest -q"]` (`name` becomes the first word of the command). Elements without `run`, or invalid elements, fail verify with `FAIL config`.
- Full logs are saved to `/work/logs/`; only a summary of failures is printed to the console.
- Right after a new install, `verify.commands` is empty (`[]`). Register your own build and test commands (you can also ask Copilot: "register the standard build and test commands for this stack in `verify.commands`").

| Stack | Example |
|---|---|
| .NET | `dotnet build --nologo`, `dotnet test --nologo` |
| Python | `python -m ruff check .`, `python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`, `go test ./...` |

## 4.7 Project-specific checks (`extensions.checks` / `scripts/ext/`)

To add project-specific checks to the data-layer checks (`rdcheck.py`, `rdfix.py`, `verify.py`), do not edit toolkit files (`scripts/*.py`, `scripts/metadata.json`). Register them in one of these two ways. Registrations are not overwritten by toolkit updates (including `--force`).

1. Write `{"module": "project_checks", "function": "check_integrations", "target": "rdcheck"}` in `extensions.checks`. `module` is a module name importable from `scripts/`; `target` is `rdcheck`, `rdfix`, or `both` (when omitted).
2. Put the file in `scripts/ext/*.py`. Public functions (not starting with `_`; only those in `CHECKS = [...]` if present) are loaded automatically. The target comes from the function attribute `target` or the file's `TARGET` (default `both`).

A check has the form `f(root, cfg)` and returns a list of findings. Empty (or `None`) means pass. A finding is `{"level": "ERROR", "chk": "PRJ-01", "loc": "docs/integrations.md:7", "msg": "…"}`, a `(level, chk, loc, msg)` tuple, or a string. The output has the same `ERROR <check> <location> <message>` form as the standard checks. `WARN` does not affect the exit code.

For each extension it calls, `verify.py` prints one line `EXT <module>.<function> target=… result=pass|warn|fail …`. A registered extension that is never called becomes an `EXT-WARN` line. Extensions that cannot be loaded or that raise an exception fail with `ERROR EXT-LOAD` / `EXT-ERROR`.

On a toolkit update, `tools/install.py` looks for wiring you added directly to `scripts/*.py` and prints what the update would drop as `WARN-WIRING  <file>:<line>`. If you see it, register the check again using one of the methods above.

## 4.8 Removed configuration keys (when updating from 0.5.x)

In 0.6.0 (EABK Lite), the following run- and hook-based keys are gone. The installer does not rewrite an older version's settings. A normal update leaves these keys in place, but they are no longer read. To remove them, recreate the settings from defaults with `--clean` (clean install) or delete them by hand ([9.4](09-versioning.en.md#94-updating-from-an-older-version-clean-install)).

| Removed key | Use in 0.5.x |
|---|---|
| `gates` | Role-based hook gates (G-1 to G-6), verify before ending, classification of external tools |
| `limits` | Time budget of a run (`max_hours` and so on) |
| `credits` | Estimate of AI credits |
| `worktree_share` | Sharing dependency directories between worker worktrees |
| `prompt_prefix` | Automatic preamble added by a hook |
| `work.retention_days` | The 14-day cleanup of `/work` (no longer exists) |
| `toolkit-unit` in `verify.commands` | Test of the removed `clean-work.py` |
| `studio-ui` in `verify.commands` (`python -m pytest -q EABK-Studio/tests`) | EABK Studio's tests. `EABK-Studio/tests/` is no longer installed into targets |

`.github/ebak-prompt-prefix.md` and the hook files (`.github/hooks/quality-gates.json`, `.github/hooks/prompt-prefix.json`, `scripts/hooks/gate.py`) are no longer read. When updating from an older version, `--clean` deletes them too.

## 4.9 Using MCP servers, plugins, and extensions

The tools and skills of the MCP servers, plugins, and extensions you have set up in GitHub Copilot can be used by your usual Copilot (the default agent) and by rd-auditor with no extra configuration. Examples are Work IQ (internal mail, meetings, chats, documents), Microsoft Learn, and the Azure MCP Server.

- **Where to configure**: Per user (VS Code user settings, `~/.copilot/`, GitHub Copilot app **Customize** → **MCP**) or per repository (`.vscode/mcp.json`, GitHub repository settings). Do not put credentials in the repository; pass them through each user's sign-in or environment variables. The toolkit does not ship MCP server settings.
- **Recording sources**: Facts obtained from internal information are recorded with their source in the source ledger (SRC-ID) of the requirements definition (skill `requirement-definition`). People without the same tools can follow the same information from the requirements definition alone.
- **Changes to external systems**: EABK Lite does not block external changes (sending mail, creating tickets, creating resources, deploying). Copilot's usual confirmation (tool approval) decides.
- **Restricting rd-auditor**: If you write `tools:` in the frontmatter of `.github/agents/rd-auditor.agent.md`, tools not listed (including MCP server tools) can no longer be used. To add them, list them in the form `<server name>/*`.

## 4.10 Changing rules, agents, and skills

- **Rules**: The installer writes a rules block into `AGENTS.md` and `.github/copilot-instructions.md`, between `<!-- ebak-abk:begin -->` and `<!-- ebak-abk:end -->`. The text between the markers is rewritten on every update. Write your project's own rules outside the markers.
- **Look of the screens**: EABK does not prescribe a design system. Write the one you want (for example "Fluent 2 for the web" or "follow the company brand guide") in the default constraints of the requirements definition or in your request.
- **Agents and skills**: You can edit `.github/agents/rd-auditor.agent.md` and `.github/skills/*/SKILL.md` directly. Re-running the installer does not overwrite locally modified files (`KEEP-LOCAL`). To take in a new version, check with `--dry-run`, then merge the diff by hand or use `--force` (which keeps `.ebak-backup-*`).
- **Models**: EABK does not specify models. To pin rd-auditor to a model, write `model:` in its frontmatter.

## 4.11 CI

`.github/workflows/ebak-verify.yml` (ebak-verify) runs `scripts/verify.sh --show-warnings` on pull requests and on pushes to main. The check scope follows `checks.profile` (lite by default). It is the same check as your local `python scripts/verify.py`, so the rules in AGENTS.md are confirmed on every push, whoever made the change and on whichever PC. Add the toolchain your app build needs (such as `actions/setup-node`) before the verify step. You can also add CodeQL or dependency scanning to this workflow.

### Data-layer repair (CI does not repair)

CI only checks and never repairs the data layer (`ebak-verify` has contents read permission only). If the data-layer check fails, run the common entry point `python scripts/rdfix.py --full --apply` locally, which checks again, and push the repair in the same change (exit codes 0/1/2 are in [05](05-scripts-reference.en.md)). The requirements definition and `docs/integrations.md` are never changed. The installer also calls this entry point once after installing. `--no-repair` checks and plans only (writes nothing); `--skip-verify` neither checks nor repairs.

Why CI does not repair: CI that only reads needs no write permission, and a bot pushing fixes onto someone's PR branch makes the branches of other people and PCs diverge. The `.github/workflows/ebak-data-layer.yml` shipped by earlier versions (repair commits and Issues) is deleted when you update from an older version with `--clean` (clean install; [9. Versioning](09-versioning.en.md)). To leave the workflow out at install time, pass `--no-ci`.
