import time
from .config import AUTO_STEP_SECONDS, PROFILES
from .logging import info
from .profiles import set_auto_index

def auto_tuner():
    info("Auto tuner starting")
    set_auto_index(0)
    for target in range(1, len(PROFILES)):
        time.sleep(AUTO_STEP_SECONDS)
        set_auto_index(target)
    info("Auto tuner reached max profile; auto negotiation finished")
