#!/system/bin/sh
set -u
export PATH="/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"
unset LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT PYTHONPATH PYTHONHOME TMPDIR
umask 077
BASE="/data/local/RootStart/Services/halagent"
RUN="$BASE/run"
LOGS="$BASE/logs"
PIDFILE="$RUN/halagent.pid"
AGENT="$BASE/halagent.py"
PY="/data/data/com.termux/files/usr/bin/python"
LOG="$LOGS/launcher.log"
mkdir -p "$RUN" "$LOGS"

if [ -x "$BASE/stop.sh" ]; then "$BASE/stop.sh" >/dev/null 2>&1 || true; fi

if [ ! -x "$PY" ]; then echo "halagent: missing python $PY" >&2; exit 1; fi
if [ ! -f "$AGENT" ]; then echo "halagent: missing $AGENT" >&2; exit 1; fi

# RootStart may be launched from a Termux-derived shell. Do not leak a custom
# linker path into Termux Python/Android tooling.
env -u LD_LIBRARY_PATH -u LD_PRELOAD PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$AGENT" >>"$LOG" 2>&1 &
pid=$!
echo "$pid" > "$PIDFILE"

sleep 1
if ! kill -0 "$pid" 2>/dev/null; then
  echo "halagent: failed; see $LOG" >&2
  rm -f "$PIDFILE"
  exit 1
fi
echo "halagent: started pid=$pid"
