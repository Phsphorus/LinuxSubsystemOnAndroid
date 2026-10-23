# LSA phone shell

lsa-shell is the Debian-side X11 phone user interface.  The real Android-facing
Termux:X11 desktop remains LXDE on display :0.  The shell starts through VNC on
display :1, where its layout can change without moving the live display path.

The first session uses the installed Openbox window manager.  It reserves room
for permanent status and navigation bars, maximises normal application windows,
and gives the shell standard X11 task control.  It can later be replaced by a
Matchbox-derived LSA window manager without moving UI logic into Android.

The initial milestone provides a home grid, app launchers, status and navigation
bars, an X11 task list, polite task close, and edge-swipe task cycling.  Task
cards have no pixels yet: static last-seen images are the first milestone.
Live previews can follow once an appropriate capture path is available.
