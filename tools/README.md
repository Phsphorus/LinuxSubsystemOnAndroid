# Build tools

The public tree intentionally does not include phone-specific SSH, deployment,
or asset-import helpers. Those helpers belong in an operator's private local
workspace and must never be committed with credentials or device state.

The included scripts build LSA's payloads and deployable package. Set
`ANDROID_NDK_ROOT` for the Android NDK and, when needed, `CYGWIN_ROOT` and
`LSA_X11_WORKSPACE` as described in the repository README.
