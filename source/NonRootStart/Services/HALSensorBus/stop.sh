#!/data/data/com.termux/files/usr/bin/sh

DIR="/data/data/com.termux/files/home/NonRootStart/Services/HALSensorBus"
PID="$DIR/run/HALSensorBus.pid"

if [ ! -f "$PID" ]; then
    echo "HALSensorBus: stopped"
    exit 0
fi

pid="$(cat "$PID" 2>/dev/null)"

if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null || true
fi

rm -f "$PID"

echo "HALSensorBus: stopped"
