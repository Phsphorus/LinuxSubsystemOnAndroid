from .cpu import cpu_low, cpu_cap900, cpu_normal, cpu_get
from .microphone import mic_start, mic_stop, mic_status
from .speaker import vol_set, spk_play, spk_stop
from .audio import audio_sink_start, audio_sink_stop
from .video import cam_video_start, cam_video_stop
from .mode import mode_get, mode_set  # LSA_MODE_CONTROLLER

def dispatch_cmd(cmd: str, args) -> str:
    if cmd == "CPU_LOW": return "OK" if cpu_low() else "ERR"
    if cmd == "CPU_CAP900": return "OK" if cpu_cap900() else "ERR"
    if cmd == "CPU_NORMAL": return "OK" if cpu_normal() else "ERR"
    if cmd == "CPU_GET": return cpu_get()
    if cmd == "MIC_START": return mic_start()
    if cmd == "MIC_STOP": return mic_stop()
    if cmd == "MIC_STATUS": return mic_status()

    if cmd == "VOL_SET":
        return vol_set(args[0], args[1]) if len(args) >= 2 else "ERR need_stream_level"
    if cmd == "SPK_PLAY": return spk_play(" ".join(args)) if args else "ERR need_path"
    if cmd == "SPK_STOP": return spk_stop()
    if cmd == "AUDIOSINK_START": return audio_sink_start(args)
    if cmd == "AUDIOSINK_STOP": return audio_sink_stop()
    if cmd == "CAM_VIDEO_START": return cam_video_start(args[0] if args else "video")
    if cmd == "CAM_VIDEO_STOP": return cam_video_stop()

    # LSA_MODE_CONTROLLER
    if cmd == "MODE_GET":
        return mode_get()

    if cmd == "MODE_SET":
        return mode_set(args[0]) if args else "ERR need_mode"

    return "ERR unknown_cmd"
