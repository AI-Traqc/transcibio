#!/usr/bin/env bash
# One-click launcher for Transcibio on Linux, macOS and the NVIDIA DGX Spark. Windows uses
# scripts/transcibio.ps1, which does the same. It picks the Docker setup for this machine:
#
#   DGX Spark / GB10        docker-compose.yml + docker-compose.spark.yml
#   Linux with NVIDIA GPU   docker-compose.yml + docker-compose.linux.yml
#   Linux without           docker-compose.yml + docker-compose.linux.yml + docker-compose.cpu.yml
#   macOS                   docker-compose.yml + docker-compose.cpu.yml
#
#   transcibio.sh start     what the icon does: checks, first-run setup (.env, chat model,
#                           Whisper models), start, open the browser. Then it stays open;
#                           Ctrl+C (or closing the window) stops the app.
#   transcibio.sh stop      stop the app from another terminal (sessions stay in data/)
#   transcibio.sh logs      follow the logs
#   transcibio.sh install   Linux: the "Transcibio" icon
#
# macOS: "Transcibio.command" in the repo root calls `start`. Runs on macOS's bash 3.2.
# See readme.md. The app listens on localhost only and uses the Ollama on this machine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ENV_FILE="$REPO_ROOT/.env"
UI_URL="http://localhost:8080"
HEALTH_URL="http://127.0.0.1:8080/api/v1/healthz"
OLLAMA_URL="http://127.0.0.1:11434"
DEFAULT_MODEL="gpt-oss-20b"   # keep in sync with backend/app/services/local_llm.py
HEALTH_TIMEOUT_S=600
OS="$(uname -s)"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

# Started from an icon or by double-click: keep the window open after an error so the
# message can be read; close it shortly after success.
finish() {
    local rc=$?
    if [[ "${TRANSCIBIO_FROM_DESKTOP:-0}" == "1" ]]; then
        if (( rc != 0 )); then
            echo
            read -r -p "Enter druecken zum Schliessen ..." _ || true
        else
            sleep 3
        fi
    fi
}

# Retry a command every 3 s until it succeeds; 1 after `timeout` seconds.
wait_for() {
    local timeout="$1" waited=0
    shift
    until "$@" >/dev/null 2>&1; do
        if (( waited >= timeout )); then
            return 1
        fi
        sleep 3
        waited=$((waited + 3))
    done
}

# --- Machine detection ------------------------------------------------------------------

# spark | gpu | cpu | mac. Needs a running Docker (the GPU check asks Docker for its runtimes).
detect_variant() {
    if [[ "$OS" == "Darwin" ]]; then
        echo mac
        return
    fi
    local gpus runtimes
    gpus="$(nvidia-smi -L 2>/dev/null || true)"
    if [[ -n "$gpus" ]]; then
        if [[ "$(uname -m)" == "aarch64" && "$gpus" == *GB10* ]]; then
            echo spark
            return
        fi
        # The GPU setup needs the NVIDIA Container Toolkit, which registers this runtime.
        runtimes="$(docker info --format '{{json .Runtimes}}' 2>/dev/null || true)"
        if [[ "$runtimes" == *'"nvidia"'* ]]; then
            echo gpu
            return
        fi
    fi
    echo cpu
}

variant_label() {
    case "$1" in
        spark) echo "DGX Spark" ;;
        gpu) echo "mit NVIDIA-GPU" ;;
        mac) echo "macOS" ;;
        *) echo "ohne GPU" ;;
    esac
}

compose() {  # variant, then docker compose arguments
    local variant="$1" files f
    shift
    case "$variant" in
        spark) files="docker-compose.yml docker-compose.spark.yml" ;;
        gpu) files="docker-compose.yml docker-compose.linux.yml" ;;
        cpu) files="docker-compose.yml docker-compose.linux.yml docker-compose.cpu.yml" ;;
        mac) files="docker-compose.yml docker-compose.cpu.yml" ;;
    esac
    local args=(--project-directory "$REPO_ROOT")
    for f in $files; do
        args+=(-f "$REPO_ROOT/$f")
    done
    docker compose "${args[@]}" "$@"
}

# --- Settings (.env) -------------------------------------------------------------------

# Read a value the way the backend does: process env wins, then the last line in .env.
env_value() {  # key, default
    local key="$1" default="$2" value=""
    if [[ -n "${!key:-}" ]]; then
        printf '%s' "${!key}"
        return
    fi
    if [[ -f "$ENV_FILE" ]]; then
        value="$(sed -n "s/^[[:space:]]*$key[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
            | tail -n 1 | sed -e 's/[[:space:]]*#.*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')"
    fi
    printf '%s' "${value:-$default}"
}

# Replace the `KEY=` line in .env, or append one. Portable (no `sed -i`, which differs on macOS).
set_env_value() {  # key, value
    awk -v key="$1" -v value="$2" '
        index($0, key "=") == 1 { if (!done) print key "=" value; done = 1; next }
        { print }
        END { if (!done) print key "=" value }
    ' "$ENV_FILE" >"$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
}

# First start: create .env from .env.example (laptop defaults; larger ones on a DGX Spark)
# and ask once for the optional Hugging Face token.
ensure_env() {  # variant
    if [[ -f "$ENV_FILE" ]]; then
        return
    fi
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"
    if [[ "$1" == "spark" ]]; then
        set_env_value TRANSCIBIO_OLLAMA_MODEL gemma4:26b
        set_env_value TRANSCIBIO_OLLAMA_NUM_CTX 131072
        set_env_value TRANSCIBIO_PROFILE quality
        info "Einstellungen angelegt: $ENV_FILE (DGX Spark: gemma4:26b, Whisper large-v3)"
    else
        info "Einstellungen angelegt: $ENV_FILE (Laptop: gemma4:e4b, Whisper medium)"
    fi
    if [[ -t 0 ]]; then
        echo
        echo "Sprechererkennung (optional): Hugging Face Token einfuegen."
        echo "Anleitung: readme.md, Abschnitt \"Sprechererkennung\". Spaeter aenderbar in .env."
        local token=""
        read -r -p "Token (Enter = ueberspringen): " token || true
        token="$(printf '%s' "$token" | tr -d '[:space:]')"
        if [[ -n "$token" ]]; then
            set_env_value HF_TOKEN "$token"
        fi
        echo
    fi
}

# --- Checks ----------------------------------------------------------------------------

ensure_docker() {
    command -v docker >/dev/null 2>&1 \
        || fail "Docker ist nicht installiert: https://docs.docker.com/get-docker/"
    if ! docker info >/dev/null 2>&1; then
        if [[ "$OS" == "Darwin" ]]; then
            info "Starte Docker Desktop ..."
            open -a Docker >/dev/null 2>&1 || true
            wait_for 180 docker info \
                || fail "Docker Desktop laeuft nicht. Bitte Docker Desktop oeffnen und erneut versuchen."
        else
            fail "Docker laeuft nicht oder braucht sudo. Starten: sudo systemctl start docker. Ohne sudo: sudo usermod -aG docker \$USER, danach neu anmelden."
        fi
    fi
    docker compose version >/dev/null 2>&1 || fail "docker compose fehlt. Bitte Docker aktualisieren."
}

ollama_up() { curl -fsS --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; }

ensure_ollama() {
    command -v curl >/dev/null 2>&1 || fail "curl fehlt."
    if ollama_up; then
        return
    fi
    if [[ "$OS" == "Darwin" ]]; then
        info "Starte Ollama ..."
        open -a Ollama >/dev/null 2>&1 || true
        if wait_for 30 ollama_up; then
            return
        fi
    fi
    fail "Ollama ist nicht erreichbar ($OLLAMA_URL). Installieren: https://ollama.com/download. Starten: Ollama-App oeffnen (Linux: systemctl start ollama oder ollama serve)."
}

has_model() {  # tags json, model; Ollama lists bare names as "<name>:latest"
    [[ "$1" == *"\"name\":\"$2\""* ]] && return 0
    [[ "$2" != *:* && "$1" == *"\"name\":\"$2:latest\""* ]]
}

# Download the chat model from .env on first use.
ensure_model() {
    local model tags
    model="$(env_value TRANSCIBIO_OLLAMA_MODEL "$DEFAULT_MODEL")"
    tags="$(curl -fsS --max-time 5 "$OLLAMA_URL/api/tags")"
    if has_model "$tags" "$model"; then
        info "Docker und Ollama ok (Chat-Modell: $model)."
        return
    fi
    info "Lade das Chat-Modell $model herunter (einmalig, mehrere GB) ..."
    local hint="Modellname pruefen: TRANSCIBIO_OLLAMA_MODEL in $ENV_FILE (Liste: ollama list)."
    if command -v ollama >/dev/null 2>&1; then
        ollama pull "$model" || fail "Download von $model fehlgeschlagen. $hint"
    else
        curl -fsS -X POST "$OLLAMA_URL/api/pull" -d "{\"model\":\"$model\",\"stream\":false}" \
            >/dev/null || fail "Download von $model fehlgeschlagen. $hint"
    fi
}

health_up() { curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; }

# Download every Whisper model the Settings presets use (small, medium, large-v3), so no
# preset waits for a download. Cached models are skipped; failures don't stop the start.
ensure_whisper_models() {  # variant
    info "Pruefe Whisper-Modelle (beim ersten Start ca. 5 GB) ..."
    compose "$1" exec -T backend python -m backend.app.services.whisper_prefetch \
        || info "Hinweis: Nicht alle Whisper-Modelle geladen; fehlende laedt die App bei Bedarf nach."
}

open_browser() {
    if [[ "$OS" == "Darwin" ]]; then
        open "$UI_URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$UI_URL" >/dev/null 2>&1 || true
    fi
}

# --- Commands --------------------------------------------------------------------------

# Ctrl+C or a closed window: stop the app, then leave.
stop_and_exit() {
    trap '' INT TERM HUP
    if [[ "${1:-}" == "HUP" ]]; then
        exec >/dev/null 2>&1   # the window is gone; nothing left to print to
    fi
    echo
    cmd_stop
    exit 0
}

cmd_start() {
    local variant
    trap stop_and_exit INT TERM
    trap 'stop_and_exit HUP' HUP
    ensure_docker
    variant="$(detect_variant)"
    ensure_env "$variant"
    ensure_ollama
    ensure_model
    # Create the bind-mount dir as the user; Docker would create it owned by root.
    mkdir -p "$REPO_ROOT/data"
    info "Starte Transcibio ($(variant_label "$variant")). Der erste Start dauert eine Weile ..."
    if ! compose "$variant" up -d --build; then
        [[ "$variant" == "gpu" ]] || fail "Start fehlgeschlagen. Logs: $SCRIPT_PATH logs"
        info "Start mit GPU fehlgeschlagen, starte ohne GPU ..."
        variant=cpu
        compose "$variant" up -d --build || fail "Start fehlgeschlagen. Logs: $SCRIPT_PATH logs"
    fi
    info "Warte, bis Transcibio bereit ist ..."
    if ! wait_for "$HEALTH_TIMEOUT_S" health_up; then
        compose "$variant" ps
        fail "Transcibio nach ${HEALTH_TIMEOUT_S}s nicht bereit. Logs: $SCRIPT_PATH logs"
    fi
    ensure_whisper_models "$variant"
    open_browser
    echo
    info "Transcibio laeuft: $UI_URL"
    info "Dieses Fenster offen lassen. Beenden: Strg+C druecken."
    # Wait until Ctrl+C, or until the app is stopped elsewhere (`stop`, another window).
    while [[ -n "$(compose "$variant" ps -q backend 2>/dev/null)" ]]; do
        sleep 5 &
        wait $! || true
    done
    info "Transcibio wurde beendet."
}

cmd_stop() {
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        info "Docker laeuft nicht, Transcibio ist also schon gestoppt."
        return
    fi
    info "Stoppe Transcibio ..."
    # --profile nemotron: also stop the optional Nemotron server on the Spark (~36 GB),
    # which plain `down` would leave running because its profile isn't active by default.
    compose "$(detect_variant)" --profile nemotron down --remove-orphans
    info "Transcibio ist gestoppt."
}

cmd_logs() {
    compose "$(detect_variant)" logs -f
}

# The icon opens a terminal that runs `start`; Ctrl+C there stops the app.
write_desktop_file() {
    local path="$1"
    cat >"$path" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Transcibio
Comment=Transcibio starten (lokal, Docker). Beenden: Strg+C im Fenster.
Exec=env TRANSCIBIO_FROM_DESKTOP=1 /bin/bash "$SCRIPT_PATH" start
Path=$REPO_ROOT
Icon=audio-input-microphone
Terminal=true
Categories=Office;
EOF
    chmod +x "$path"
}

cmd_install() {
    if [[ "$OS" == "Darwin" ]]; then
        info "macOS braucht keine Installation: Transcibio.command im Projektordner."
        return
    fi
    local apps_dir="$HOME/.local/share/applications"
    local desktop_dir
    desktop_dir="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
    mkdir -p "$apps_dir" "$desktop_dir"

    write_desktop_file "$apps_dir/transcibio.desktop"
    cp "$apps_dir/transcibio.desktop" "$desktop_dir/transcibio.desktop"
    chmod +x "$desktop_dir/transcibio.desktop"
    gio set "$desktop_dir/transcibio.desktop" metadata::trusted true 2>/dev/null \
        || echo "Hinweis: Icon ggf. per Rechtsklick > 'Start erlauben' freigeben." >&2
    # Older versions installed a separate stop icon.
    rm -f "$apps_dir/transcibio-stop.desktop" "$desktop_dir/transcibio-stop.desktop"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
    fi
    info "Icon \"Transcibio\" angelegt (Desktop und App-Übersicht)."
}

main() {
    case "${1:-}" in
        start) trap finish EXIT; cmd_start ;;
        stop) trap finish EXIT; cmd_stop ;;
        logs) cmd_logs ;;
        install) cmd_install ;;
        *)
            echo "Usage: $(basename "$0") start|stop|logs|install" >&2
            exit 2
            ;;
    esac
}

main "$@"
