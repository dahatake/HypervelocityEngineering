[日本語](01-first-steps.md) | **English**

# S1 Getting Started

## Prerequisites before you start

If you meet the following, you can use HVE Studio. Items that have been confirmed are separated from items that cannot currently be confirmed from the supporting documents.

| Item | Prerequisite | Basis / confirmation status |
|---|---|---|
| Python | Python 3.9 or later is required. | Confirmed: [`README.md`](../../HVE-Studio/README.md) |
| Additional installation | No additional Python packages are needed. three.js for 3D display is bundled. Git repository analysis requires the `git` command. | Confirmed: [`README.md`](../../HVE-Studio/README.md), `repo_scan.py` |
| Launch script | You can use `start.ps1` on Windows and `start.sh` on macOS/Linux. The range of operation checks per OS version is unconfirmed. | Confirmed: [`start.ps1`](../../HVE-Studio/start.ps1), [`start.sh`](../../HVE-Studio/start.sh) |
| Browser | A browser that can open a local URL is required. Supported browser names and versions are unconfirmed. | Confirmed: the specification opens a browser at launch. Supported range is unconfirmed. |
| Target repository | Specify a repository that has EABK management data (any location where `docs/requirements-definition.md` or `docs/catalog.md` can be found), or a git repository without EABK (code mode; see "Using Studio without EABK" below). | Confirmed: [`README.md`](../../HVE-Studio/README.md) |
| Network | No internet connection is needed. Studio listens only on `127.0.0.1`, and the default port is `8765`. | Confirmed: [`README.md`](../../HVE-Studio/README.md) |
| Permissions / network settings | Whether administrator rights, firewall/proxy settings, or permission to use a local port are required is unconfirmed. If they become necessary, ask your organization's device or network administrator. | Unconfirmed |

## Launching

Open a terminal in the target repository's folder and run the following.

```powershell
python HVE-Studio/studio.py
```

To launch from another location, specify the target.

```powershell
python HVE-Studio/studio.py --repo C:\path\to\your-repo
```

To start from the screen that suits your role, add `--role` (`pm` = Dashboard, `architect` = 2D map, `swe` = Tables). To only check, before launching, whether the data layer can be found, use `--check`.

```powershell
python HVE-Studio/studio.py --role architect
python HVE-Studio/studio.py --check
```

The browser opens and shows `http://127.0.0.1:8765/` (if that port is in use, the next number; check the URL shown in the terminal). To stop, press `Ctrl+C` in the terminal.

The startup splash shows application loading, source and project data analysis, and preparation of the initial view. Progress represents completed stages, not an estimate of files or remaining time. If loading fails, the error and a retry action are shown.

On Windows you can also launch with `.\HVE-Studio\start.ps1 <repository>`, and on macOS / Linux with `./HVE-Studio/start.sh <repository>`. Options can be passed as `-Role pm`, `-Check`, `-NoOpen` in PowerShell, and in the shell like `./HVE-Studio/start.sh . 8765 --role pm`.

Role-specific walkthroughs are in [05-product-manager.en.md](05-product-manager.en.md), [06-architect.en.md](06-architect.en.md), and [07-software-engineer.en.md](07-software-engineer.en.md).

## Your first 10 minutes

1. Look at the **Dashboard**. It shows the number of requirements, the share approved, the share with implementation registered, unanswered questions, and BLOCKED (stalled requirements).
2. Click a bar in "Implementation progress by goal." The requirements belonging to that goal are highlighted on the map.
3. On the **2D map**, scroll the wheel to zoom in and out, and drag to move. Point at a dot and the items directly connected to it light up.
4. Click a dot. Details (requirement text, acceptance criteria, implementation files, tests) appear on the right. Press `Esc` to clear.
5. In the search box at the top of the screen (press `/` to jump to it), enter a word you're curious about (e.g., "login") and pick a result. Related items are highlighted in the diagram.
6. Press `JA | EN` at the top right and confirm the language switches.

## Viewing another repository

Press the repository name and select a folder in the OS dialog. No restart is needed. Any local Git repository, including empty or document-only repositories, or a folder with management records can be opened. Invalid targets show a reason and keep the current repository.

## Using Studio without EABK (code mode)

Studio can also show a git repository without EABK (FR-1086). From a clone of HVE (this toolkit), pass the root of the target repository:

```powershell
python HVE-Studio/studio.py --repo C:\path\to\any-git-repo --check
python HVE-Studio/studio.py --repo C:\path\to\any-git-repo
```

`--check` prints a `mode: code (...) requirement-docs=… requirements=… linked-to-code=… code-files=… test-files=… components=…` line and exits 0.

- Management records remain authoritative and are supplemented with local Git inventory and explicit code references. Git analysis requires the `git` command.
- If not, Studio derives a read-only model: requirement IDs (`FR-…`, `NFR-…`) from the first column of markdown tables and from headings (`docs/PRD.md` and files whose names contain prd, requirement, 要求 or spec are read first), the code and test files that mention each ID (catalog rows: implementation files / tests), and source files grouped into components (shared parts).
- Existing views remain available. Written acceptance criteria are preserved and missing information is not guessed.
- Empty Git repositories are supported. Folders with neither management records nor Git are not scanned and exit 1 with a reason.
- Without `--repo`, Studio opens the current folder if it has a data layer or is a git repository showable in code mode, otherwise Studio's own repository.
- Example: on `C:\GitHub\VideoCreator` it showed 103 requirements from `docs/PRD.md`, 56 of them linked to code or tests, 78 code files, and 6 components.

Open **Repository analysis & tasks** from Dashboard to inspect files, dependencies, Git history, diagnostics and checklist/TODO tasks. New tasks and status changes persist in Studio-owned storage without changing originals. See the [data reference](08-data-reference.en.md) for coverage, exclusions and storage. No LLM is used.
