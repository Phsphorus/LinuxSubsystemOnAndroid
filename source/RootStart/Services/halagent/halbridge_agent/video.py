from .logging import log

def cam_video_start(name: str):
    log("CAM_VIDEO_START requested but not implemented")
    return "ERR cam_video_not_supported"

def cam_video_stop():
    log("CAM_VIDEO_STOP requested but not implemented")
    return "ERR cam_video_not_supported"
