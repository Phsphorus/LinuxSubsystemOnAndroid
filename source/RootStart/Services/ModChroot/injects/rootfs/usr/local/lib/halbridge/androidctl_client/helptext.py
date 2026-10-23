HELP_TEXT = """androidctl usage:

  androidctl mic-rec <name>
      Start continuous microphone recording with the given name.
      Recording will run until you call `androidctl mic-rec stop`.

  androidctl mic-rec stop
      Stop continuous microphone recording and copy the last recording
      into ~/DCIM/Audio/Captured inside the chroot.

  androidctl spk-play <file>
      Copy the given audio file into the Android bridge and play it on
      the phone using termux-media-player.

  androidctl spk-stop
      Stop any active playback triggered via spk-play.

  androidctl vol <music|ring|alarm|stream> <0-15>
      Set Android volume for the given stream to the specified level.

  androidctl sink start [--format FMT --rate HZ --channels N]
      Ask Android to start the negotiated HALAudio sink and report the PCM port.

  androidctl sink stop
      Ask the Android audio provider to stop its output sink.

  androidctl cpu low
      Force LITTLE cluster to ~500 MHz and BIG cluster to ~725 MHz.
      Uses auto detected CPU clusters on the phone.

  androidctl cpu cap900
      Cap all CPUs to 900 MHz maximum with min 500 MHz.

  androidctl cpu normal
      Restore default governor schedutil for all CPUs.

  androidctl cpu get
      Query current frequencies for all CPUs.

  androidctl help
      Show this help text.

Camera and location are no longer androidctl data commands. Linux clients use:
  http://127.0.0.1:8765/camera.mjpg
  http://127.0.0.1:8765/snapshot.jpg
  gpsd on 127.0.0.1:2947

RootStart/LSA framework lifecycle selects and controls those providers.
"""
