#!/data/data/com.termux/files/usr/bin/sh

DIR="/data/data/com.termux/files/home/NonRootStart/Services/HALSensorBus"
PY="/data/data/com.termux/files/usr/bin/python"
PID="$DIR/run/HALSensorBus.pid"
LOG="$DIR/logs/HALSensorBus.log"

mkdir -p "$DIR/run" "$DIR/logs"

if [ -f "$PID" ]; then
    old="$(cat "$PID" 2>/dev/null)"

    if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
        echo "HALSensorBus: already running pid=$old"
        exit 0
    fi

    rm -f "$PID"
fi

nohup "$PY" "$DIR/HALSensorBus.py" >>"$LOG" 2>&1 &
pid=$!

echo "$pid" > "$PID"

sleep 1

if ! kill -0 "$pid" 2>/dev/null; then
    echo "HALSensorBus: failed"
    tail -n 30 "$LOG"
    rm -f "$PID"
    exit 1
fi

echo "HALSensorBus: started pid=$pid port=8560"
