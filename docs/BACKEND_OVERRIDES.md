# Backend rejection and forced fallback

`lsectl` separates support from administrative selection policy. A backend may be technically supported and still be rejected by an operator for diagnosis, containment of a runtime fault, or explicit lower-tier testing.

## Controls

Run the control client inside the active ModChroot mount namespace:

```sh
lsectl report --verbose
lsectl reject <backend-id> [reason]
lsectl disable <backend-id> [reason]
lsectl accept <backend-id>
lsectl enable <backend-id>
lsectl rejections
```

The commands operate on the stable backend ID, not a model name, provider name, or public tier letter. `disable` and `enable` are aliases.

## Semantics

The selector preserves two independent facts:

| Fact | Values |
|---|---|
| Probe/support | `AVAILABLE`, `UNSUPPORTED`, `ERROR` |
| Administrative policy | `ACCEPTED`, `REJECTED` |
| Runtime | `STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, `FAILED` |

For example, rejecting a functioning GPU Tier A is reported as `AVAILABLE` plus `REJECTED BY USER`. It is not `UNSUPPORTED`. The next accepted candidate is then considered normally. If the previously selected backend was running, the control client stops it, refreshes selection, and starts the replacement. It does not start an unrelated stopped optional backend merely because its policy changed.

Rejections persist in `RootStart/Services/ModChroot/state/backend-rejections.tsv` with owner-only state permissions. They survive ordinary NonRootStart/RootStart restarts and are cleared only by `accept`/`enable` or deliberate state administration. Package deployment does not ship a user's rejection ledger.

## N6000 proof

The N6000 test rejected `storage.android-shared` with a diagnostic reason. Its probe remained `AVAILABLE`, Tier-Z `storage.termux-shared` was selected and reached `RUNNING`, and that selection survived a controlled root restart. Accepting the Tier-A backend returned Storage to Tier A and left the ledger empty.
