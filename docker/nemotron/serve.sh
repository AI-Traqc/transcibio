#!/usr/bin/env bash
# Entrypoint of the Nemotron container (docker-compose.spark.yml): runs the vLLM command it is
# given and, while that process lives, refreshes a heartbeat file every 5 s. vLLM opens its
# port only after loading and warming up the model (several minutes); until then the backend
# reads this file (data/models/nemotron/.server-status.json) and Settings shows "starting".
# A file older than 30 s counts as stopped (backend: STATUS_STALE_SECONDS), so a killed
# container doesn't look like it is still starting.
set -u

status_file="${TRANSCIBIO_STATUS_FILE:-/models/.server-status.json}"
started_at="$(date +%s)"
stopping=""

"$@" &
server_pid=$!

# docker stop / Ctrl+C: stop the heartbeat and pass the signal on to vLLM.
trap 'stopping=1; kill -TERM "$server_pid" 2>/dev/null' TERM INT

while [[ -z "$stopping" ]] && kill -0 "$server_pid" 2>/dev/null; do
    printf '{"started_at": %s}\n' "$started_at" >"$status_file.tmp" &&
        mv -f "$status_file.tmp" "$status_file"
    sleep 5 &
    wait $!  # interruptible by the trap, unlike a plain `sleep`
done

rm -f "$status_file"
wait "$server_pid"
exit_code=$?
# A signal can interrupt the first wait (status > 128) before vLLM has exited.
while kill -0 "$server_pid" 2>/dev/null; do
    wait "$server_pid"
    exit_code=$?
done
exit "$exit_code"
