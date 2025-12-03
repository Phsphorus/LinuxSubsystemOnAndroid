# LSA
Linux Subsystem on Android - LSA

REQUIREMENTS:

root

Should work on any android with root

SELinux should not have to be set to permissive, we work within the bounds of SELinux naturally -- subject to change

------

Objective:

Near native Linux on android that can access hardware.

Completed:

GPS

Camera -- photos only 

Speakers/Bluetooth -- Full Audio Routing

Microphone recordings

-------

My current queue is:

VirGL + Java App + Touch control -- Active Devolopment | Priority

Make a OpenGL shim and GL compositor | Scrapped, I got like 90% done before I realised I could do something better

Live Microphone recording 

PhoneUI -- Active Devolopment 

Touch and Gestures

Camera -- Video Capture 

---------
NOTICE: Dev rootfs not avalible yet (its like 32gb i've gotta find a mirror)
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

--------

Syntax & Command usage:

"androidctl" typed into any terminal will enact debain to puppet android, this will be turned into a full UI in the future

androidctl cam-snap -- takes a picture and puts it at /home/user/DCIM/Pictures/Camera

androidctl mic-rec -- takes a microphone recording and puts it at /home/user/DCIM/Audio/Captured | DEGRADED

androidctl mic-rec stop -- stops microphone recording

androidctl cam-video -- starts camera video capture | NOT SUPPORTED YET

androidctl vol -- list of volumes to change

androidctl vol music 1-15 -- changes sound volume

androidctl vol ring 1-15 -- changes ring volume

androidctl vol alarm 1-15 -- changes alarm volume


HALAudio automatically chooses the best buffer sizes for stable, low-latency audio.
You normally do not need to run HALAudio up or HALAudio down.

"HALAudio" typed into any terminal will puppet HALAudio

HALAudio status -- shows status and buffer chosen

HALAudio up -- will tighten buffers 

HALAudio down -- will loosen buffers

