# Calvin Schoolwork

An add-on for Claude Code that helps with Calvin engineering coursework. It knows how particular Calvin courses want lab memos, reports and problem sets laid out, it helps you write and debug EES, and it checks your numbers with a calculator it can rerun before you hand anything in. It explains the method as it goes, so you can use it to learn the material and not only to produce the document.

It is not a grader and it does not know every course equally well. Ask it "which courses do you know?" and it will tell you how much it has for each one.

## What you need

- **Claude Code**, with a Claude account that includes it. Install it from [claude.com/claude-code](https://claude.com/claude-code).
- **Python 3.10 or newer.** On a Mac, the simplest way is to install it from [python.org](https://www.python.org/downloads/). On Windows, install it from the same page and tick **"Add python.exe to PATH"** on the first screen of the installer.
- **Access to this repository on GitHub.** It is private for now. If you were invited as a tester, accept the GitHub invitation first. Claude Code uses your computer's GitHub login to download it; if the install below says it cannot find or clone the repository, that login is the missing piece.

## Install

Open Claude Code, then type these two lines into Claude Code itself (not into a separate terminal), one at a time:

    /plugin marketplace add EphraimDykstra/calvin-autonomy
    /plugin install schoolwork@calvin-autonomy

That is the whole install. There is nothing to clone and no script to run by hand.

## Using it

1. Make a folder for your coursework, for example `Documents/Coursework`.
2. Open Claude Code in that folder. On a Mac, open the Terminal app and type `cd ~/Documents/Coursework` then `claude`. On Windows, open PowerShell and type `cd ~\Documents\Coursework` then `claude`.
3. Ask for what you need, in plain words: "Help me write the ENGR 328 lab 2 memo", "My EES code won't converge", "Explain how to pick the state points for this cycle".

**The first time**, it sets itself up before answering. That downloads about 250 MB and can take several minutes. After that it takes a few seconds.

It creates two folders inside your coursework folder: `workspace/`, where your course files and finished work are kept, and `.calvin-autonomy/`, which holds its tools. Both stay on your computer. Updating or removing the add-on never touches them. What you type, and any file you ask Claude to read, is sent to Claude as part of the conversation, exactly as it is when you use Claude for anything else.

## What it cannot do

- **It cannot run EES.** It writes the EES code and tells you exactly what to run and what numbers to bring back.
- **It does not read handwriting on its own.** For a photo of a handwritten worksheet, Claude reads the photo itself and asks you to confirm what it says. Automatic text recognition is only for batches of scanned printed pages. It uses RapidOCR, which installs with everything else, or Tesseract if you already have it.
- **Coverage varies by course.** Where it has little for a course, it says so and asks for a handout or a graded example, rather than inventing a format.
- **Windows is untested.** Everything here has been run on a Mac. The Windows setup script is written but has never been run on Windows. If setup fails on Windows, please report what it printed.

Check what it gives you before you submit it. It shows you which course convention it followed and where that came from, so you can check.

## Installing from a clone instead

If you would rather work from a copy of the repository:

    git clone https://github.com/EphraimDykstra/calvin-autonomy.git
    cd calvin-autonomy
    ./scripts/bootstrap.sh

On Windows, run the last step as:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

Then open Claude Code in that folder. The script is safe to run again at any time. Its last line, `CALVIN_BOOTSTRAP {...}`, says what is installed and what is missing.

## For developers

Generic Claude Code and Codex workflows help students configure a private workspace, ingest course material, find relevant prior examples, and complete supported assignments. Course evidence drives methods and formats; the host agent supplies reasoning while the CLI preserves provenance and checks.

### Quick start without the bootstrap script

    python3 -m venv .venv
    .venv/bin/python -m pip install -e '.[dev,ocr]'
    .venv/bin/python scripts/setup.py --project-root . --workspace workspace
    .calvin-autonomy/bin/coursework --workspace workspace doctor --project-root .
    .calvin-autonomy/bin/coursework --workspace workspace init

Open the repository in Claude Code or Codex. The installed project instructions route uploaded assignments through the completion and verification workflow. Import each course with bounded limits, then use the course-profile curator once to capture reviewed course-specific methods and deliverable conventions before starting assignments. Rendered files must be visually inspected and verified before submission.

Setup installs discoverable Claude Code and Codex skills plus a project-local CLI launcher into the project root while private course material, memory, and assignment runs remain under `workspace/`. The runtime resolves evidence and durable review records against the same-course catalog, binds checks, independent verification, and artifacts to the current solution hash, parses requested deliverable formats, and requires a structured visual inspection before reporting ready.

### How the plugin install works

`.claude-plugin/marketplace.json` makes this repository a Claude Code plugin marketplace whose one plugin, `schoolwork`, is the repository root. Claude Code loads `skills/` and the three agents listed in `.claude-plugin/plugin.json`. A plugin install cannot run code, so the `schoolwork` skill runs `scripts/bootstrap.sh --plugin-data "${CLAUDE_PLUGIN_DATA}"` on first use:

- The venv lives in the plugin data directory, which survives plugin updates. The package is installed editable from the current plugin copy, and every bootstrap run re-points it, because Claude Code moves the plugin to a new versioned cache folder on each update.
- `workspace/` and the launcher live in the student's own folder. `scripts/setup.py --plugin` refuses to create a project or workspace inside the plugin cache or data store, because Claude Code deletes the cache on update and the data store on uninstall. It also copies no skills into the project, so each skill appears once.
- `scripts/bootstrap.ps1` is the Windows twin and prints the same `CALVIN_BOOTSTRAP` keys. It has not been run on Windows.

Current limits: arbitrary engineering correctness, scanned-equation interpretation, handwriting recognition, discipline software, LMS submission, and autonomous use of missing data are not promised. Automatic OCR of printed scans (RapidOCR by default, Tesseract when installed) imports text as unreviewed; hash-bound transcription import is available for reviewed image content. The built-in renderer produces deterministic PDF, DOCX, XLSX, and plot artifacts; course-specific active spreadsheet formulas still require their own validated adapter. No public license is selected by this starter repository.

### Turning on the forbidden-name scan

`scripts/check_distribution.py` always checks tracked files for structural identity keys and absolute home-directory paths. It scans for **real people's names only when you supply them**, through an environment variable, so the names themselves never enter a tracked file:

Set `CALVIN_FORBIDDEN_NAMES` to the names you want flagged, then run `scripts/check_distribution.py`. Separate entries with `;` or newlines, not commas, since a `Surname, Given` form is itself a name.

This page deliberately shows no example value. Any literal name written here would live in a tracked file, and configuring that same name would make the scan flag this README, correctly. That is also why the names belong in an environment variable rather than a config file: a file in the tree is a file the audit has to read. Names shorter than three characters are refused, because a shorter value cannot identify anyone and matches inside ordinary words. The audit says which scan actually ran:

    distribution audit passed (forbidden-name scan: not run, CALVIN_FORBIDDEN_NAMES is not set)
    distribution audit passed (forbidden-name scan: 2 names, clean)

Unset, the scan does not run and the audit says so rather than implying it passed.

**Do not put the test fixtures' invented names in this variable.** Several test files deliberately contain invented names as detector fixtures (`tests/test_identity.py`, `tests/test_adaptation.py` and `tests/test_distribution_names.py`), and none is audit-exempt, nor should be. Configuring those names would fail every branch.

See [docs/architecture.md](docs/architecture.md) for the public/private boundary and execution flow, and [docs/pilot-status.md](docs/pilot-status.md) for implemented capabilities, held-out evidence, and remaining validation work. The content-free [held-out evaluation harness](docs/evaluation.md) scores 10-20 private runs for false-ready behavior, blockers, requirement coverage, verification, stale detection, and observed correction time.

## License

MIT. See [LICENSE](LICENSE).
