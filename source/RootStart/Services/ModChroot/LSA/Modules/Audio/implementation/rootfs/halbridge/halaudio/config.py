PA_HOME = "/tmp/pa-home"
PA_RUN = "/tmp/pa-run"
SINK_NAME = "AndroidSink"
SINK_MONITOR = f"{SINK_NAME}.monitor"
AUDIO_HOST = "127.0.0.1"
AUDIO_PORT = 8556
CTRL_SOCK_PATH = "/tmp/halaudio.sock"
AUTO_STEP_SECONDS = 10.0
PROFILES = [
    {"name":"very_loose", "frames":2048, "pacat_latency_ms":100},
    {"name":"loose", "frames":1024, "pacat_latency_ms":60},
    {"name":"medium", "frames":720, "pacat_latency_ms":40},
    {"name":"tight", "frames":480, "pacat_latency_ms":25},
    {"name":"insane", "frames":256, "pacat_latency_ms":18},
    {"name":"ultra", "frames":192, "pacat_latency_ms":14},
    {"name":"extreme", "frames":128, "pacat_latency_ms":10},
    {"name":"hyper", "frames":96, "pacat_latency_ms":7},
    {"name":"ridiculous", "frames":64, "pacat_latency_ms":5},
    {"name":"absurd", "frames":48, "pacat_latency_ms":4},
    {"name":"meltdown", "frames":32, "pacat_latency_ms":3},
]

SOURCE_NAME = "AndroidSource"
SOURCE_HOST = "127.0.0.1"
SOURCE_PORT = 8557
SOURCE_FIFO = "/tmp/pa-run/AndroidSource.pcm"
