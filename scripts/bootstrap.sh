#!/bin/bash
# Get a student from nothing to a working install, and say plainly what is missing.
#
# Idempotent: safe to run repeatedly. Prints a JSON status block on the last
# line so the calling skill can act on it without parsing prose. Everything
# before that line is for the student to read if they want to.
# scripts/bootstrap.ps1 is the Windows twin and prints the same line.
#
# Two modes:
#   ./scripts/bootstrap.sh
#       Cloned repository. The venv is .venv here and the project is this
#       repository.
#   bootstrap.sh --plugin-data DIR [--project DIR]
#       Installed as a Claude Code plugin. This script runs from the plugin's
#       versioned cache, which is replaced on every update, so nothing may be
#       kept here: the venv goes in DIR (the plugin data directory, which
#       survives updates) and the student's workspace goes in the project
#       directory (default: the current directory).
set -uo pipefail
PROJECT_ARG=""
PLUGIN_DATA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin-data) PLUGIN_DATA="${2:-}"; shift 2 ;;
    --project) PROJECT_ARG="${2:-}"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
START_DIR="$(pwd)"
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

if [ -n "$PLUGIN_DATA" ]; then
  MODE="plugin"
  mkdir -p "$PLUGIN_DATA" || exit 1
  VENV="$(cd "$PLUGIN_DATA" && pwd)/venv"
  PROJECT="${PROJECT_ARG:-$START_DIR}"
else
  MODE="clone"
  VENV="$ROOT/.venv"
  PROJECT="${PROJECT_ARG:-$ROOT}"
fi
VPY="$VENV/bin/python"

PY=""
PY_VERSION=""
VENV_OK="false"
DEPS_OK="false"
CLI_OK="false"
RASTERIZER_OK="false"
TESSERACT_OK="false"
OCR_ENGINE="null"
OCR_VERSION="null"
NEEDS=()

say() { printf '%s\n' "$1"; }
json_str() { if [ -n "$1" ]; then printf '"%s"' "$1"; else printf 'null'; fi; }

# --- find an interpreter new enough to run this project ---------------------
# pyproject requires >=3.9, and 3.9 is what macOS ships, but 3.10-3.12 are
# preferred and 3.9 is only a last resort (see below). 3.10-3.12 come first: the OCR engine's current release (1.4.x)
# ships for those only, and on 3.13+ pip can only resolve an older 1.2.x
# release. A newer interpreter is still used when it is all there is, and the
# engine version that actually landed is reported below.
for candidate in python3.12 python3.11 python3.10 python3.13 python3.14 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    v="$("$candidate" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)" || continue
    major="${v%%.*}"; minor="${v##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
      PY="$candidate"; PY_VERSION="$v"; break
    fi
  fi
done

# uv may already hold a 3.12 even when PATH does not; use it without
# downloading anything if the best interpreter found is 3.13 or newer.
if [ -n "$PY" ] && [ "${PY_VERSION##*.}" -ge 13 ] && command -v uv >/dev/null 2>&1; then
  found="$(uv python find --no-python-downloads 3.12 2>/dev/null)"
  if [ -n "$found" ]; then PY="$found"; PY_VERSION="3.12"; fi
fi

if [ -z "$PY" ] && command -v uv >/dev/null 2>&1; then
  say "No Python 3.10+ found, but uv is available. Fetching one."
  if uv python install 3.12 >/dev/null 2>&1; then
    PY="$(uv python find 3.12 2>/dev/null)"
    [ -n "$PY" ] && PY_VERSION="3.12"
  fi
fi

# Last resort: the Python 3.9 that macOS ships. Everything runs on it; only
# the optional OCR engine resolves to an older, slightly weaker release.
if [ -z "$PY" ]; then
  for candidate in python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      v="$("$candidate" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)" || continue
      if [ "$v" = "3.9" ]; then
        PY="$candidate"; PY_VERSION="$v"
        say "Using Python 3.9. It works; a newer Python reads scanned pages a little better."
        break
      fi
    fi
  done
fi

# An existing venv keeps its interpreter; report that one, not the candidate.
if [ -x "$VPY" ]; then
  PY_VERSION="$("$VPY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || printf '%s' "$PY_VERSION")"
fi

if [ -z "$PY" ] && [ ! -x "$VPY" ]; then
  say "Could not find Python 3.9 or newer."
  say "The quickest fix on a Mac is:  brew install python@3.12"
  NEEDS+=('"python3.9+"')
  printf '\nCALVIN_BOOTSTRAP {"mode":"%s","python":null,"venv":false,"deps":false,"cli":false,"pdf_rasterizer":false,"tesseract":false,"ocr_engine":null,"ocr_engine_version":null,"needs":[%s]}\n' "$MODE" "$(IFS=,; echo "${NEEDS[*]}")"
  exit 1
fi
say "Using Python $PY_VERSION"

# --- virtual environment ----------------------------------------------------
if [ ! -x "$VPY" ]; then
  say "Creating the virtual environment."
  "$PY" -m venv "$VENV" >/dev/null 2>&1
fi
[ -x "$VPY" ] && VENV_OK="true"

if [ "$VENV_OK" != "true" ]; then
  say "The virtual environment could not be created."
  NEEDS+=('"venv"')
else
  # --- dependencies --------------------------------------------------------
  # The ocr extra brings the PDF rasterizer and the OCR engine. It is optional
  # to the package but wanted here, because scanned handouts are common and a
  # student should not have to discover a second install step later.
  # Editable, and re-run every time: in plugin mode ROOT moves on each plugin
  # update, and this re-points the venv at the current copy.
  say "Installing dependencies. The first time downloads about 250 MB and can take several minutes."
  "$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  if "$VPY" -m pip install --quiet -e "$ROOT[dev,ocr]" >/dev/null 2>&1; then
    DEPS_OK="true"
  else
    say "Dependency install failed. Re-run to retry; if it keeps failing, the error above is the reason."
    NEEDS+=('"dependencies"')
  fi
fi

# --- skills, agents, launcher and workspace ---------------------------------
if [ "$DEPS_OK" = "true" ]; then
  SETUP_ARGS=(--project-root "$PROJECT" --workspace workspace)
  [ "$MODE" = "plugin" ] && SETUP_ARGS+=(--plugin)
  if ! SETUP_ERR="$("$VPY" "$ROOT/scripts/setup.py" "${SETUP_ARGS[@]}" 2>&1 >/dev/null)"; then
    say "$SETUP_ERR"
  fi
  if [ -x "$PROJECT/.calvin-autonomy/bin/coursework" ] \
    && "$PROJECT/.calvin-autonomy/bin/coursework" --help >/dev/null 2>&1; then
    CLI_OK="true"
  fi
  [ "$CLI_OK" != "true" ] && NEEDS+=('"cli"')
fi

# --- optional capabilities --------------------------------------------------
if [ "$DEPS_OK" = "true" ]; then
  "$VPY" -c 'import pypdfium2' >/dev/null 2>&1 && RASTERIZER_OK="true"
  # The same probe the CLI uses, so this line and `doctor` cannot disagree.
  engine_json="$("$VPY" -m engineering_assistant.ocr --engine 2>/dev/null | tail -n 1)"
  OCR_ENGINE="$(printf '%s' "$engine_json" | "$VPY" -c 'import json,sys
try: v=json.load(sys.stdin).get("engine")
except Exception: v=None
print(json.dumps(v))' 2>/dev/null || printf 'null')"
  OCR_VERSION="$(printf '%s' "$engine_json" | "$VPY" -c 'import json,sys
try: v=json.load(sys.stdin).get("version")
except Exception: v=None
print(json.dumps(v))' 2>/dev/null || printf 'null')"
fi
command -v tesseract >/dev/null 2>&1 && TESSERACT_OK="true"

if [ "$OCR_ENGINE" = "null" ]; then
  say ""
  say "Optional: scanned pages cannot be read automatically; no OCR engine is installed."
  say "Scanned handouts will wait for you to confirm what they say."
  NEEDS+=('"ocr"')
fi

say ""
if [ "$CLI_OK" = "true" ]; then
  say "Ready."
else
  say "Not ready yet. See above."
fi

printf 'CALVIN_BOOTSTRAP {"mode":"%s","python":%s,"venv":%s,"deps":%s,"cli":%s,"pdf_rasterizer":%s,"tesseract":%s,"ocr_engine":%s,"ocr_engine_version":%s,"needs":[%s]}\n' \
  "$MODE" "$(json_str "$PY_VERSION")" "$VENV_OK" "$DEPS_OK" "$CLI_OK" "$RASTERIZER_OK" "$TESSERACT_OK" "$OCR_ENGINE" "$OCR_VERSION" "$(IFS=,; echo "${NEEDS[*]:-}")"

[ "$CLI_OK" = "true" ]
