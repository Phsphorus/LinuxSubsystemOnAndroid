# Removable-storage ownership

LSA treats a USB mass-storage partition as a filesystem ownership decision. It
does not claim the whole USB bus, so HID, SDR, serial, and other USB devices
remain outside this module.

The Storage lifecycle polls Android `vold` every three seconds. It reads only
public-volume state and acts per partition.

| Android `vold` result | Owner | Debian location | Behavior |
|---|---|---|---|
| `MOUNTED` with a usable public `path` | Android | `/media/android/<label>-<uuid>` | LSA bind-mounts Android's visible path. Android and Debian see the same mounted filesystem; Debian never raw-mounts it. |
| `UNMOUNTABLE`, `fsType=ntfs` | Debian | `/media/debian/<label>-<uuid>` | LSA resolves only that public partition through sysfs and mounts it with Debian `ntfs-3g`. Android receives no LSA path or second mount. The preferred mount is read-write with the normal Debian desktop user's ownership; LSA falls back to read-only only when NTFS cannot mount writable. |
| `UNMOUNTABLE` with another filesystem | Nobody yet | None | LSA records it as `unhandled` and leaves it untouched until a specific Debian driver is implemented and tested. |

The desktop user receives two Home-directory entries:

- `Android Storage` -> `/media/android`
- `Debian Storage` -> `/media/debian`

They are ordinary paths, so PCManFM and other Linux file managers can browse
them without a custom file-manager plugin. The live ownership table is readable
inside Debian at `/run/lsa/storage-volumes.tsv`.

Unmount and eject remain Android's responsibility for Android-owned media. For
Debian-owned NTFS, LSA's watcher removes the Debian mount when Android no
longer reports that public partition. This implementation does not auto-mount
an arbitrary raw block device and does not give Debian ownership merely because
an item appears on USB.

## N6000 witnessed case

Kingston DataTraveler 3.0 partition `public:8,49` appeared as Android `vold`
`UNMOUNTABLE`, `fsType=ntfs`, label `MEOW`, UUID `50561161561148DC`. LSA mapped
that partition to `/dev/block/sdd1`, mounted it read-write through `ntfs-3g`,
and verified that Debian `myuser` could create, read, and remove a private
sentinel at `/media/debian/MEOW-50561161561148DC`. Android did not mount the
volume.
