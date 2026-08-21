#!/bin/sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${WORKOUT_GATE_DIR:-$HOME/.workout-gate}"
mkdir -p "$HOME_DIR"

# Plugin cache paths move on updates, so the launcher resolves through the latest SessionStart root.
echo "$ROOT" > "$HOME_DIR/app-path"

BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/vibe-crunch"
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" <<'EOF'
#!/bin/sh
RT="${WORKOUT_GATE_DIR:-$HOME/.workout-gate}"
APP="$(cat "$RT/app-path" 2>/dev/null || true)"
[ -f "$APP/workout_gate/micro.py" ] || APP="$RT/app"
[ -f "$APP/workout_gate/micro.py" ] || { echo "Vibe Crunch runtime not found; start a new Codex/Claude session first." >&2; exit 1; }
PY="$RT/venv/bin/python"
[ -x "$PY" ] || PY="$APP/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 2>/dev/null || true)"
[ -x "$PY" ] || { echo "python3 is required." >&2; exit 1; }
cd "$APP" && exec "$PY" -m workout_gate.micro "$@"
EOF
chmod +x "$LAUNCHER"

# SessionStart stays silent because its stdout is injected into model context.
exit 0
