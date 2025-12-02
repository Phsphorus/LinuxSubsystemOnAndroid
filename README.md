# LSA
Linux Subsystem on Android - LSA

REQUIREMENTS:
root
Should work on any android with root

Objective:
Near native Linux on android that can access hardware.

Completed:

GPS

Camera -- photos only 

Speakers/Bluetooth -- Full Audio Routing

My current goals are:

Make a custom Xserver for true GPU acceleration

Microphone recording

PhoneUI

Touch and Gestures

Camera -- Video Capture 

---------

If installing Dev rootfs

Instructions:

Android

run HALAudioS.py under termux no root at /data/data/com.termux/files/home (or any sub folder you choose)

run halagent.py at /data/local/halbridge (if not made, make it) as root

put the rootfs at /data/local/linux

run ./start-chroot.sh in /data/local/linux as root

--------
If installing manual rootfs

Instructions:

Good luck bro, i documented some of it, read the Manualinstall.txt and pray i didnt document it wrong
