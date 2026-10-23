# LSA Wireless

`Modules/Wireless` is LSA's baseline wireless-capability module.  It is a
generic Android module: neither phone model nor vendor identity selects a
provider or backend.

## Scope

The first backend deliberately exposes the Android-owned, Linux-visible host
network interface without taking it down or changing its association.  When a
mounted rootfs can see that interface in `/sys/class/net`, Tier A
`wireless.host-interface` presents ordinary Linux networking: the existing
interface, normal sockets, routing, and standard `/sys`/`/proc` counters.

Tier Z `wireless.termux-uplink` is an honest compatibility fallback.  It
preserves ordinary Linux socket use through the Termux/Android uplink when the
direct host-interface presentation is unavailable.  It does not claim mesh,
IBSS, P2P, NAN, monitor mode, or raw-frame transport.

Future peer transports use independently tracked raw primitives rather than a
single optimistic "raw radio" flag:

```
wireless.raw.remain_on_channel
wireless.raw.cancel_remain_on_channel
wireless.raw.mgmt_tx
wireless.raw.mgmt_tx_status
wireless.raw.mgmt_rx_registration
wireless.raw.mgmt_rx
wireless.raw.action_tx
wireless.raw.action_rx
```

A raw peer backend may become available only when every primitive in its own
contract is operationally verified.  An advertised interface mode or a
successful frame transmission is never enough to promote a bidirectional raw
transport.

## Inventory and evidence

The Android-generic provider writes a mode-0600 structured runtime TSV.  Its
rows separate support from evidence:

- Support: `AVAILABLE`, `UNSUPPORTED`, `UNKNOWN`, `ERROR`, or `UNVERIFIED`.
- Evidence: `ADVERTISED`, `PROBED`, `OPERATIONALLY_VERIFIED`, or
  `UNVERIFIED`.

It safely inventories PHY bands/frequencies, interface modes, mesh and IBSS
advertisement, P2P framework evidence, Android Wi-Fi Aware feature
advertisement, raw primitive state, numeric concurrency facts when exposed,
and standard link metrics.  `iw` is the primary generic nl80211 tool.  The
deployer installs it through Termux and materialises its executable plus the
two required `libnl` libraries into a root-owned LSA path, because Android
root cannot safely execute a private Termux-app binary under SELinux
Enforcing.  Android package-feature discovery is bounded; the provider
intentionally does not make `dumpsys wifi` availability a startup dependency.

`lsectl report --verbose` includes the full Wireless capability section.
`lsectl health Wireless` validates the selected backend's owned runtime state.
As with every module, `lsectl reject wireless.host-interface <reason>` keeps
an otherwise available Tier A visible as rejected and exercises the next
accepted candidate; `lsectl accept wireless.host-interface` restores policy.

## Qualification and safety boundary

Ordinary inventory is non-destructive.  It records the interface carrying a
real route lookup and never repurposes it merely to refresh a report.

The first startup after deployment instead performs a bounded aggressive
qualification by default.  It uses only `lsaq*` interfaces that it creates,
records raw `iw` evidence, tests generic interface creation/concurrency and
remain-on-channel where possible, and removes every owned interface before
returning Android Wi-Fi to normal operation.  Results are mode-0600 JSON plus
root-only evidence under `Services/ModChroot/state/wireless`, keyed by the
kernel release, Android build/incremental version, `iw` hash, and the LSA
qualification schema.  A changed radio-relevant context causes requalification;
an unrelated LSA update does not.

Use these controls:

```sh
lsectl wireless status
lsectl wireless qualify          # deliberate aggressive requalification
lsectl wireless qualify --safe   # record safe-only discovery
lsectl wireless qualification disable
lsectl wireless qualification enable
lsectl wireless qualification status
```

The supported generic helper `lsa-nl80211` exists only because `iw` has no
arbitrary `NL80211_CMD_FRAME` transmit command.  It is architecture-selected
(`arm64` or `armv7`), source-available, uses bounded arguments/output, and
reports TX submission and any observed TX-status cookie.  It never upgrades a
raw transport on its own: a peer-visible action frame and a matching receive
path remain separately required.

Mesh creation/join, IBSS creation/join, NAN publish/subscribe/data paths,
P2P group lifecycle, and raw-frame testing remain distinct conclusions.  A
failed destructive test is kept as `UNSUPPORTED` or `ERROR` with its exact
driver/tooling cause; it is never collapsed into an optimistic advertisement.
That backend must track and clean up only interfaces, sessions, sockets,
TUN/TAP devices, and helper processes it created.  Android Wi-Fi may be
disrupted during qualification, but normal startup uses the cached result and
does not repeat that cost.

When a peer transport cannot naturally appear as a kernel network interface,
its future backend should use an LSA-owned TUN/TAP data plane so Linux clients
continue to use normal IP, UDP, TCP, and sockets.  Mesh routing, PeerLink,
and application-level topology are intentionally outside this module.
