#!/bin/sh
# Run hook-adjacent code so plugin-cache updates cannot be shadowed by a stale shared runtime.
# System python3 is sufficient because the default micro-workout path is stdlib-only.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="${WORKOUT_GATE_DIR:-$HOME/.workout-gate}"
PY="$RT/venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 2>/dev/null || true)"
[ -x "$PY" ] || exit 0
exec "$PY" "$ROOT/hooks/micro_gate.py"
