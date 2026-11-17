#!/bin/bash
# macOS: double-click in Finder to start Transcibio. The window stays open; Ctrl+C stops the app. See readme.md.
exec env TRANSCIBIO_FROM_DESKTOP=1 /bin/bash "$(dirname "$0")/scripts/transcibio.sh" start
