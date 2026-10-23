import shutil
import subprocess

def run(cmd, check=False, capture=False, env=None):
    if capture:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    else:
        result = subprocess.run(cmd, env=env)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed {cmd} rc={result.returncode} err={getattr(result, 'stderr', '')}")
    return result

def which(name: str):
    return shutil.which(name)

def read_exact(stream, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = stream.read(size - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)
