# Security policy

## What counts as a security issue here

git-signoff is a gate. Anything that lets an attestation pass the gate
without the claim it makes being true is a security issue:

- The verifier (`skills/git-signoff/verify_signoff.py`, the `verify/` action)
  accepting an attestation it should reject — a trailer-injection path, an
  anchoring rule that covers a commit or tree it should not, a merge-commit
  check that lets unreviewed changes through.
- The producer (`skills/git-signoff/attest.py`) writing an attestation it
  should refuse — free text that becomes a second trailer, a status not
  derived from the transcript bytes, a transcript snapshot that is not this
  conversation's (the approval marker exists to close that).
- The initializer (`init.py`) writing outside the repository, through a
  symlink, or over user content.
- Anything that exposes transcript contents beyond the reviewer's machine
  without their action.

Out of scope, by design and stated in the docs: a human or agent *with push
rights* deliberately writing a false attestation. Structural verification
cannot distinguish that from a true one; authenticity needs an identity the
agent does not hold (reviewer signing, or a service-created commit) and is
tracked as an open item in `docs/roadmap.md`, not a vulnerability.

## Reporting

Please use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**) rather than a public issue. Include
the verifier or producer version (`verify_signoff.py --version`,
`attest.py --version`), a minimal repository or conformance-vector-style
payload that reproduces the problem, and the verdict you expected.

You should hear back within 7 days. Fixes to the verifier ship as a new
`verify-vX.Y` pin tag with a note in `verify/README.md` telling earlier pins
to move; the `CHANGELOG.md` entry names the issue class. Where a fix changes
what a valid attestation is, a conformance vector is added so third-party
implementations can check themselves.

## Supported versions

Pin tags never move, so every pin keeps running the behavior it had. Only
the newest `verify-v1.x` and `init-vN` receive fixes; the verifier prints a
one-line warning in CI when a newer pin than the one running exists.
