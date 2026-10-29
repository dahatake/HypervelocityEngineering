[日本語](04-customization.md) | **English**

# 4. Configuration and Customization

Settings are consolidated in `scripts/ebak.config.json`. When you install or update, the values you have set are preserved and only new keys are added.

## 4.1 Build, static analysis, and test commands (`verify.commands`)

After checking the managed data (CHK-01 to 27), `scripts/verify.py` runs the commands registered here in order. If even one fails, it exits with 1.

```json
"verify": {
  "timeout_sec": 1800,
  "commands": [
    { "name": "install", "run": "npm ci" },
    { "name": "lint", "run": "npm run lint" },
    { "name": "build", "run": "npm run build" },
    { "name": "unit", "run": "npm test -- --run" },
    { "name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true, "timeout_sec": 900 }
  ]
}
```

| Key | Meaning |
|---|---|
| `name` | Display name. Also used for the log file name |
| `run` | Shell command executed at the repository root |
| `slow` | If `true`, the command is skipped in the worker gate (`verify.py --quick`) and runs only at integration time and in the final stage |
| `timeout_sec` | Timeout for this command (default is `verify.timeout_sec`) |
| `cache_files` | Example: `["package.json", "package-lock.json"]`. If these files have not changed since the last success, this command is skipped (intended for dependency installation such as `npm ci`; disabled with `--no-cache`). Register it separately from build |

A failure caused by the environment that matches `verify.retry_on` (a regular expression; the default covers things like vitest's `Timeout calling` and `ECONNRESET`) is automatically retried once. To disable this, set `verify.retry_flaky: false`.

You can also write only strings, as in `"commands": ["python -m pytest -q"]`. In that case, `name` becomes the first word of the command (for example, `python`). An element without `run`, or an element that is neither a string nor an object, makes verify fail with `FAIL config`.

Examples by technology stack:

| Stack | Example |
|---|---|
| .NET | `dotnet build --nologo`, `dotnet test --nologo` |
| Python | `python -m ruff check .`, `python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`, `go test ./...` |

Full logs are saved in `/work/runs/<run-id>/logs/` (or `/work/logs/` when there is no run), and only a summary of failures is printed to the console.

## 4.2 Model selection

EABK does not specify a model. Both the conductor and the workers call task without the `model` argument and leave the selection to Copilot (such as Copilot Fusion). The models actually used are recorded in `work/runs/<run-id>/models.jsonl` and appear under "Models actually used" in `kpi.py run`. If you want to pin a specific model, write `model:` in the frontmatter of each `.github/agents/*.agent.md`.

**Item granularity**: `queue add` rejects an item with more than 12 ACs (an exception can be made with `--allow-large`). In actual measurements, rework was concentrated in items whose working time exceeded 200 minutes.

## 4.3 Tuning the gates (`gates`)

```json
"gates": {
  "enabled": true,
  "subagent_verify": {
    "implementer": ["--quick"],
    "test-designer": ["--docs-only"],
    "rd-author": ["--docs-only"]
  },
  "subagent_verify_max_blocks": 3,
  "agent_stop_max_blocks": 40,
  "enforce_conductor_edit_scope": true
}
```

| Key | Meaning |
|---|---|
| `enabled` | If `false`, all hook gates are disabled (verify's checks remain). Use only when isolating a cause |
| `subagent_verify` | Arguments of the verify run before a worker finishes (G-4). Workers not listed here are not checked |
| `subagent_verify_max_blocks` | Upper limit on how many times the same worker is sent back. When exceeded, the result is returned with `GATE G-4` attached, and the conductor does not integrate that result |
| `agent_stop_max_blocks` | Upper limit on how many times a conductor that has not met the completion conditions is sent back when it tries to finish |
| `enforce_conductor_edit_scope` | Rejects the conductor editing anything other than `work/` and `docs/run-history.md`. Set to `false` only when subagent detection does not work in the harness ([07-troubleshooting.en.md](07-troubleshooting.en.md)) |
| `deploy_patterns` | Regular expressions for commands regarded as deployment. If specified, it **replaces** the default (`DEFAULT_CONFIG` in `scripts/ebaklib.py`), so copy the default first and then add to it |
| `external_write_verbs` | Among the tools of MCP Servers, plugins, and extensions, those whose names contain one of these verbs (`create`, `update`, `delete`, `send`, `do_action`, and so on) are regarded as "changes to an external system" (G-5. [4.4](#44-using-mcp-servers-plugins-and-extensions)). If specified, it **replaces** the default |
| `external_deploy_verbs` | Likewise, tools whose names contain one of these verbs (`deploy`, `provision`, `publish`, `release`) are regarded as "deploy/publish" and are judged by the value of `deploy` |
| `external_tool_allow` | Regular expressions of tool names that are not regarded as changes to an external system (example: `"^mcp_myindex_update_index$"`). Use it to allow a tool whose name contains a verb but that acts only locally |

## 4.3b Time, dependency sharing, and credit settings (`limits` / `worktree_share` / `credits`)

```json
"limits": { "max_hours_default": 2.5, "max_hours_cap": 3, "reserve_minutes": 30 },
"worktree_share": { "enabled": true, "dirs": ["node_modules"] },
"credits": { "default_multiplier": 1, "model_multipliers": { "claude-sonnet-5.5": 1, "gpt-6.1-sol": 3 } }
```

| Key | Meaning |
|---|---|
| `limits.max_hours_default` | Time (in hours) used when run_options has no `max_hours` |
| `limits.max_hours_cap` | Upper limit of `max_hours`. A value above this is truncated. To run for a long time overnight, raise this value (and `max_hours` in run_options) (for example, `8`). The default is 3 hours |
| `limits.reserve_minutes` | Time reserved for stage 6 (the final stage). When the remaining time falls below this (or elapsed time exceeds 85%), no new items are started |
| `worktree_share.enabled` / `dirs` | Makes the dependency directories of working worktrees (such as `node_modules`) links (junctions on Windows) to the real directories in the main working tree where they are already installed, eliminating `npm ci` for each worktree. Sharing happens only when `package.json` and `package-lock.json` are the same as in the share source. If there is no share source, `integrate.py prepare` prints a `NOTE:`, so install once in the main working tree. Can be disabled with `false` |
| `credits.model_multipliers` | When `run-state.py finish` is run without `--credits`, records an "estimate" in the AI credits column of run-history, counting worker (task) calls by model multiplier. Calls by the conductor itself are not included. The duration of each worker is recorded in `work/runs/<run-id>/subagents.jsonl` |

Hooks immediately allow read-only and record-only tools (`view`, `grep`, `sql`, `report_intent`, and so on) without reading settings or the repository.

## 4.4 Using MCP Servers, plugins, and extensions

The tools and skills of the MCP Servers, plugins, and extensions that you have configured in GitHub Copilot are available to the conductor and all workers with no additional configuration. Examples are Work IQ (internal email, meetings, chat, and documents), Microsoft Learn, the Azure MCP Server, and the Copilot Studio and Microsoft 365 Agents Toolkit plugins.

- **How it works**: The frontmatter of `.github/agents/*.agent.md` does not contain `tools:`. In Copilot CLI and GitHub, omitting `tools` enables all tools, including those of configured MCP Servers. In VS Code, the tools you have enabled in the tool picker are used. If you write `tools:`, tools that are not listed (including MCP Server tools) become unavailable. To restrict by role, list the required MCP Servers in the form `<server-name>/*` in addition to the built-in tools.
- **Where to configure**: Register MCP Servers and plugins either per user (VS Code user settings, settings in `~/.copilot/`, `copilot plugin install`, or **Customize** → **MCP** / **Plugins** in the GitHub Copilot app) or in the repository (`.vscode/mcp.json`, GitHub repository settings). The GitHub Copilot app automatically uses the settings for Copilot CLI (`~/.copilot/`) and the repository settings. For anything that needs credentials, do not put secrets in the repository; pass them through each user's sign-in or environment variables. The toolkit does not distribute MCP Server settings.
- **How to use**: You do not need to name tools in your request, such as "use Work IQ to look up related meetings and emails". The skills (requirement-definition and implement-fr) instruct the agents to use MCP Servers and skills for internal information, official documentation, and the target technology when they are available. Facts obtained from internal information are recorded with their sources in the source ledger (SRC-ID). As a result, later people and agents that do not have the same tools can trace the same information from the requirements definition alone.
- **Environments without the tools**: No particular tool is assumed to exist. If one is unavailable, proceed with ordinary search and the materials in `<references>`, and record something like "internal information not verified".
- **Changes to external systems**: Reads (search, fetch, questions) are always allowed. External changes, such as sending email, creating tickets, or creating, updating, or deleting cloud resources or Copilot Studio agents, are allowed during a run only when run_options has `external_write: する` (yes). Deploy/publish is allowed only with `deploy: する` (yes). Both are enforced by hooks (G-5). rd-auditor and reviewer are read-only regardless of run_options. Among the built-in tools of the GitHub Copilot app, `rename_session` and `send_session_message`, which act only within the app, are not regarded as external changes. `rename_branch`, which renames the session's branch, is rejected only during a run because it would change the integration branch.
- **Tool count limit**: In VS Code, up to 128 tools can be enabled per request. If registering many MCP Servers exceeds the limit, disable unused servers in the tool picker.

## 4.5 Other settings

| Key | Default | Meaning |
|---|---|---|
| `management_files` | `docs/requirements-definition.md` and others | Paths of the managed data. Can be changed to match an existing directory layout |
| `enterprise_data_catalog` | None (unset) | Optional. The reference source of the enterprise data catalog. `{"source": "<file path or http(s) URL>", "name_column": "<name column/field (optional)>", "format": "auto|csv|json|markdown|html (optional)"}`. `scripts/entities.py check` / `todo` cross-check it read-only. Credentials cannot be embedded in the URL (in that case the result is "cannot be verified"). The fetch wait time is PARAM-016, and the similarity threshold for variant candidates is PARAM-015 |
| `base_branch` | `main` | The merge target branch. Used for diff checks (CHK-12/13) and for rejecting pushes (G-5) |
| `work.retention_days` | 14 | Retention period in days for `/work/runs/` |
| `checks.ambiguous_words` | 適切, 迅速, 直感的, etc. (Japanese ambiguous words such as "appropriate", "prompt", "intuitive") | List of ambiguous words (CHK-13) |
| `checks.id_scan_exclude` | `docs/**`, `EABK-Studio/**`, etc. | Paths excluded when searching code for requirement IDs (CHK-17/19) |
| `checks.test_path_pattern` | tests/, *.test.*, etc. | Paths regarded as test code (CHK-09) |

## 4.6 Look and feel of screens (design system)

The requirements definition writes only "what must be satisfied"; it does not specify colors, decoration, or UI libraries. The implementer decides the look and feel according to "Look and feel of screens (UI design foundation)" in the `implement-fr` skill.

- **Default**: Use the latest official design system and official components of the target platform. These are Microsoft Fluent 2 (Fluent UI) for the web, WinUI 3 for Windows, the Human Interface Guidelines and SwiftUI standard components for Apple platforms, and Material 3 for Android. If the repository already has a design system, it takes precedence.
- **Consistency**: In the first item that builds a screen, the theme (light, dark, high contrast), design tokens, and the application shell are listed in the catalog's common components as the "design foundation". The conductor orders the other screen items after this item, and the reviewer checks screen diffs against the rules.
- **When you want to specify one**: Write in your request something like "use Fluent 2 as the design system" or "follow the internal brand guide (attached)", or pass the guidelines in `<references>`. rd-author records it in the requirements definition as a default constraint, and the implementer gives it top priority.
- **When you want to fix the look of an existing app**: Request "migrate the existing screens to the design foundation". Updating only the procedure documents does not change screens that have already been built.

## 4.7 Changing agents and procedures

- The behavior of each role is defined in `.github/agents/*.agent.md`, and the detailed procedures are defined in `.github/skills/*/SKILL.md`. You may edit them directly.
- Re-running the install script does not overwrite files you have modified locally (`KEEP-LOCAL`). To take in a newer version of the toolkit, check with `--dry-run` and then merge the differences by hand, or use `--force` (which leaves a backup).
- The body of each skill is the full text of the three original Prompts (RequirementDefinition creation, RD-FR_Prompt, and SystemTest-Increment-Run). The "translation table" at the top absorbs the differences between the original Prompts and unattended execution. If you revise an original Prompt, replace the body and leave the translation table as it is.

## 4.8 CI

`.github/workflows/ebak-verify.yml` runs `scripts/verify.sh --show-warnings`, triggered by pull requests and pushes to main. Add the toolchain needed to build the app (such as `actions/setup-node`) as a step before verify. If you add CodeQL or dependency scanning, add it to this workflow as well.

### Data layer workflow (ebak-data-layer)

`.github/workflows/ebak-data-layer.yml` (ebak-data-layer) runs `python scripts/verify.py --docs-only` on pull requests, pushes to main, manual runs (workflow_dispatch), and a weekly schedule, and checks the data layer.

- On failure, it automatically repairs through the common entry point `python scripts/rdfix.py --full --apply` and re-checks (the same entry point as the installer and manual runs; it has no rewrite procedure of its own. For exit codes 0/1/2, see [05](05-scripts-reference.en.md)). By default, the installer calls the same entry point once after installation; `--no-repair` performs only the check and plan (no writes), and `--skip-verify` performs neither check nor repair. The design is that automatic repair does not change the requirements definition (`docs/requirements-definition.md` is restored after repair). The repair is committed only if the check passes. For a pull request from the same repository, it is pushed to that PR's branch; for pushes to main and scheduled runs, it is pushed to the repair branch `eabk/data-layer-fix` and a PR is created (none is added if one already exists).
- If it is still not fixed after repair, an Issue with the label `eabk-data-layer` is created, containing a summary of the failure and a link to the run. If an unresolved Issue with the same content exists, a comment is added.
- The permissions are only write on contents, pull-requests, and issues. For pull requests from forks, only the check is performed and nothing is written. The bot's repair commits are not repaired again.
- To disable it, delete this file or Disable this workflow on the GitHub Actions page. If you do not want it installed, specify `--no-ci` at install time.

## 4.9 Compute resources and the cloud

**Match parallelism to CPU and memory.**
- `parallel_workers: auto` (the default) allocates one implementer per 2 cores and 6 GB, up to 8. The number resolved by `run-state.py start` is left in `meta.json`.
- Each worker is given CPU threads as "number of cores × 1.5 ÷ number of workers" (`HVE_CPUS`; 4 for 20 cores and 8 workers). At the same time, the environment variables for the main test runners' settings are also passed (`VITEST_MAX_WORKERS`, `VITEST_MAX_THREADS`, `VITEST_MAX_FORKS`, `PYTEST_XDIST_AUTO_NUM_WORKERS`, `CARGO_BUILD_JOBS`, `GOMAXPROCS`, `CMAKE_BUILD_PARALLEL_LEVEL`, `MAKEFLAGS`). Values already set by the user are not overwritten.
- Measurements (the project's vitest with 8 parallel workers on 20 cores): letting each use all cores took 361 seconds and produced one test timeout. Limiting each to 2 threads took 404 seconds (slower), and 4 threads each took 371 seconds with no timeouts. That is why a slightly generous allocation is used. The `Timeout calling "onTaskUpdate"` in the previous run appeared in about 10% of the unit logs, in a situation where workers at a parallelism of 5 were also under load from things like browsers. For tools that do not read environment variables, such as Playwright, read it in the config file, as in `workers: Number(process.env.HVE_CPUS) || undefined`.

**Run checks concurrently.**
- In `verify.commands`, adding `"parallel": true` to consecutive steps runs them at the same time (for example, lint, type check, and unit tests). Do not add it to steps that need a previous step, such as build.
- System Tests run concurrently with `ledger.py run --jobs N|auto` (or `system_test.jobs` in the settings). The default is `auto` (number of CPUs ÷ 4, between 2 and 6). A case with `"serial": true`, or whose command contains a string from `system_test.serial_patterns` (default: `default_port`), runs alone after the parallel run finishes. Cases with the same command are run only once and the result is shared. Furthermore, when two or more commands point to the same pytest file (in the form `python -m pytest <file>[::node] [-k expression] [-q]`), they are run together in one pytest process (`-k` uses the same grammar as pytest, and results are distributed to each case from the JUnit output), and only the cases that failed and the cases that matched no test are re-run individually (the judgment and logs are as before). In actual measurement (45 cases including GUI), this went from 320 seconds to 281 seconds. To turn it off, use `ledger.py run --no-batch` or `system_test.batch_pytest: false`. Canary and serial cases are not batched. Changing a fixture that starts the GUI server for each test (function scope) to module scope makes it even faster (after confirming that test state remains isolated). The canary always runs first and alone.

**Azure is not used by default.** The user chooses it only when all of the following conditions are met (it is not implemented as a runtime option).
1. The local machine is small (fewer than 8 cores or less than 32 GB of memory).
2. In `kpi.py run`, the effective parallelism does not reach `parallel_workers`, and the cause is a lack of CPU (the duration of verify and System Tests dominates).
3. Waiting for model responses (LLM time) is not dominant. Adding cloud VMs does not shorten LLM wait time.

In the previous measurements, most of the non-LLM time was the serial section of integration, duplicated checks, and excessive parallelism in test runners. These can be resolved with the settings above and the cache, and no VM was needed. If you run only the checks on an Azure VM (for example, a 32-core Dev/Test), place the working tree on the VM, set `parallel_workers` to match the VM's core count, and allow the charges (paid_services) in the run options.
