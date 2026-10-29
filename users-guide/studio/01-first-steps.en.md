[日本語](01-first-steps.md) | **English**

# S1 Getting Started

## Prerequisites before you start

If you meet the following, you can use EABK Studio. Items that have been confirmed are separated from items that cannot currently be confirmed from the supporting documents.

| Item | Prerequisite | Basis / confirmation status |
|---|---|---|
| Python | Python 3.9 or later is required. | Confirmed: [`README.md`](../../EABK-Studio/README.md) |
| Additional installation | No additional installation is needed. three.js for 3D display is bundled. | Confirmed: [`README.md`](../../EABK-Studio/README.md) |
| Launch script | You can use `start.ps1` on Windows and `start.sh` on macOS/Linux. The range of operation checks per OS version is unconfirmed. | Confirmed: [`start.ps1`](../../EABK-Studio/start.ps1), [`start.sh`](../../EABK-Studio/start.sh) |
| Browser | A browser that can open a local URL is required. Supported browser names and versions are unconfirmed. | Confirmed: the specification opens a browser at launch. Supported range is unconfirmed. |
| Target repository | Specify a repository that has EABK management data. Any location where `docs/requirements-definition.md` or `docs/catalog.md` can be found can be the target. | Confirmed: [`README.md`](../../EABK-Studio/README.md) |
| Network | No internet connection is needed. Studio listens only on `127.0.0.1`, and the default port is `8765`. | Confirmed: [`README.md`](../../EABK-Studio/README.md) |
| Permissions / network settings | Whether administrator rights, firewall/proxy settings, or permission to use a local port are required is unconfirmed. If they become necessary, ask your organization's device or network administrator. | Unconfirmed |

## Launching

Open a terminal in the target repository's folder and run the following.

```powershell
python EABK-Studio/studio.py
```

To launch from another location, specify the target.

```powershell
python EABK-Studio/studio.py --repo C:\path\to\your-repo
```

To start from the screen that suits your role, add `--role` (`pm` = Dashboard, `architect` = 2D map, `swe` = Tables). To only check, before launching, whether the data layer can be found, use `--check`.

```powershell
python EABK-Studio/studio.py --role architect
python EABK-Studio/studio.py --check
```

The browser opens and shows `http://127.0.0.1:8765/` (if that port is in use, the next number; check the URL shown in the terminal). To stop, press `Ctrl+C` in the terminal.

On Windows you can also launch with `.\EABK-Studio\start.ps1 <repository>`, and on macOS / Linux with `./EABK-Studio/start.sh <repository>`. Options can be passed as `-Role pm`, `-Check`, `-NoOpen` in PowerShell, and in the shell like `./EABK-Studio/start.sh . 8765 --role pm`.

Role-specific walkthroughs are in [05-product-manager.en.md](05-product-manager.en.md), [06-architect.en.md](06-architect.en.md), and [07-software-engineer.en.md](07-software-engineer.en.md).

## Your first 10 minutes

1. Look at the **Dashboard**. It shows the number of requirements, the share approved, the share with implementation registered, unanswered questions, and BLOCKED (stalled requirements).
2. Click a bar in "Implementation progress by goal." The requirements belonging to that goal are highlighted on the map.
3. On the **2D map**, scroll the wheel to zoom in and out, and drag to move. Point at a dot and the items directly connected to it light up.
4. Click a dot. Details (requirement text, acceptance criteria, implementation files, tests) appear on the right. Press `Esc` to clear.
5. In the search box at the top of the screen (press `/` to jump to it), enter a word you're curious about (e.g., "login") and pick a result. Related items are highlighted in the diagram.
6. Press `JA | EN` at the top right and confirm the language switches.

## Viewing another repository

Press the repository name at the top right of the screen and enter a folder path. You don't need to restart. For a folder without an EABK data layer, a message appears and the view doesn't switch.
