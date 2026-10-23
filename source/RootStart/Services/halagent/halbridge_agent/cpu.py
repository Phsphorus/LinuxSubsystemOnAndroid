import os
from .logging import log

LITTLE = []
BIG = []
CPU_IDS = []

def detect_cpu_clusters():
    global LITTLE, BIG, CPU_IDS
    base_dir = "/sys/devices/system/cpu"
    cpus = []
    try:
        for name in sorted(os.listdir(base_dir)):
            if not name.startswith("cpu") or not name[3:].isdigit():
                continue
            idx = int(name[3:])
            cpufreq_dir = os.path.join(base_dir, name, "cpufreq")
            maxf = 0
            try:
                with open(os.path.join(cpufreq_dir, "cpuinfo_max_freq")) as f:
                    txt = f.read().strip()
                    if txt:
                        maxf = int(txt)
            except Exception:
                pass
            cpus.append((idx, maxf))
    except Exception as e:
        log(f"CPU detect ERR {e}")
        cpus = []

    if not cpus:
        LITTLE = list(range(0, 6))
        BIG = list(range(6, 8))
        CPU_IDS = LITTLE + BIG
        log(f"CPU detect fallback LITTLE={LITTLE} BIG={BIG}")
        return

    CPU_IDS = [idx for idx, _ in cpus]
    cpus.sort(key=lambda p: p[1])
    max_freq = cpus[-1][1]
    if max_freq <= 0:
        LITTLE = [idx for idx, _ in cpus]
        BIG = []
    else:
        BIG = [idx for idx, f in cpus if f == max_freq]
        LITTLE = [idx for idx, f in cpus if f != max_freq]
    log(f"CPU detect LITTLE={LITTLE} BIG={BIG} CPU_IDS={CPU_IDS}")

def write_sys(path: str, value: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except Exception as e:
        log(f"write_sys ERR {path}: {e}")
        return False

def cpu_paths():
    if not CPU_IDS:
        detect_cpu_clusters()
    for i in sorted(set(CPU_IDS)):
        yield i, f"/sys/devices/system/cpu/cpu{i}/cpufreq"

def cpu_low():
    if not LITTLE and not BIG:
        detect_cpu_clusters()
    ok = True
    for i in LITTLE or sorted(set(CPU_IDS)):
        base = f"/sys/devices/system/cpu/cpu{i}/cpufreq"
        ok &= write_sys(f"{base}/scaling_min_freq", "500000")
        ok &= write_sys(f"{base}/scaling_max_freq", "500000")
    for i in BIG:
        base = f"/sys/devices/system/cpu/cpu{i}/cpufreq"
        ok &= write_sys(f"{base}/scaling_min_freq", "725000")
        ok &= write_sys(f"{base}/scaling_max_freq", "725000")
    return ok

def cpu_cap900():
    ok = True
    for _, base in cpu_paths():
        ok &= write_sys(f"{base}/scaling_min_freq", "500000")
        ok &= write_sys(f"{base}/scaling_max_freq", "900000")
    return ok

def cpu_normal():
    ok = True
    for _, base in cpu_paths():
        ok &= write_sys(f"{base}/scaling_governor", "schedutil")
    return ok

def cpu_get():
    parts = []
    for i, base in cpu_paths():
        try:
            with open(f"{base}/scaling_cur_freq") as f:
                freq = f.read().strip()
        except Exception as e:
            log(f"cpu_get ERR cpu{i}: {e}")
            freq = "?"
        parts.append(f"cpu{i}={freq}")
    return " ".join(parts)
