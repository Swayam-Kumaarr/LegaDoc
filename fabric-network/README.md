# Fabric Network

**Status: confirmed working end-to-end against a real, live network.** The
first build milestone (see SYSTEM_DESIGN.md, Build Prompt Seed) — stand
this up and confirm the Chain Worker can submit and confirm one signed hash
transaction — is done, not just attempted. `RecordHash`, `GetHash`, and
`VerifyHash` have all been run for real: a transaction committed as
`VALID` on both peers, a real record read back, and live tamper detection
confirmed (correct hash → true, tampered hash → false).

One thing changed along the way worth knowing: `workers/chain_worker/fabric_client.py`
does **not** use the `fabric-sdk-py` (`hfc`) library anymore. That library's
own dependencies turned out to be genuinely broken on any current Python —
confirmed by actually installing it, not assumed: `pysha3` (a hard pin)
doesn't compile on Python 3.10+, its bundled protobuf files predate a
breaking protoc change, and its pinned `requests`/`urllib3` versions no
longer agree with each other. Rather than keep patching an abandoned
library, `fabric_client.py` now shells out to the `peer` CLI directly via
`subprocess` — the exact same command shape proven working below, just
called from Python instead of typed by hand. See that file's docstring for
the full reasoning.

Still real, still-open work: only a 2-org network exists (the design's
Container Diagram names 5 — Police/FSL/Hospital-Medical/Court/External-
Verifiers), and this uses `test-network`'s demo CA, not a real production
PKI. Both are separate, later milestones — see the Risk Dossier for the
full list.

## What's here

```
fabric-network/
  chaincode/hashledger/
    hashledger.go   — the smart contract: RecordHash, GetHash, VerifyHash
    go.mod
  connection-profile.example.json  — template; copy to connection-profile.json once generated for real
  scripts/
    setup-test-network.sh  — brings up a local network and deploys the chaincode
```

## The chaincode

Deliberately narrow — not a generic asset-transfer sample. Three functions:

- **`RecordHash(docID, docHash, orgID)`** — writes a hash record once. If
  the same `docID` already has the *same* hash recorded, this succeeds as a
  no-op (that's what makes the Chain Worker's retry safe). If it already has
  a *different* hash, this fails loudly — a hash changing value after the
  fact is exactly what this whole system exists to make impossible.
- **`GetHash(docID)`** — read the stored record.
- **`VerifyHash(docID, hashToCheck)`** — the direct support for the
  strongest demo moment this architecture can produce: recompute a
  document's hash locally, ask the ledger if it matches, get a live
  yes/no. Do this on an untouched document, then again after deliberately
  editing the stored file, live, in front of whoever you're demoing to.

## Setting up a local test network

1. **Get `fabric-samples` and the Fabric binaries/images.** Don't hand-roll
   the network topology — Hyperledger's own bootstrap script does this
   correctly and is what `scripts/setup-test-network.sh` assumes exists:

   ```bash
   curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/bootstrap.sh | bash -s
   ```

   This downloads `fabric-samples` (including its `test-network` script)
   plus the `peer`/`configtxgen`/`cryptogen` binaries and pulls the Fabric
   Docker images. Requires Docker running.

2. **Bring up the network and deploy the chaincode:**

   ```bash
   cd fabric-network/scripts
   ./setup-test-network.sh
   ```

   This script (a) starts `fabric-samples/test-network`'s standard 2-org
   network, (b) creates a channel named `legadoc-channel` (matching
   `workers/chain_worker/worker.py`'s `_get_fabric_client()`), and
   (c) packages and deploys `chaincode/hashledger`.

   **This design's Container Diagram names 5 orgs** (Police / FSL /
   Hospital-Medical / Court / External-Verifiers). `test-network` only
   stands up 2 by default. Getting from 2 orgs to 5 is real, separate work
   (each additional org needs its own MSP, CA, and peer, and the channel
   config needs updating to add them) — do NOT treat that as done because
   the 2-org network comes up cleanly. Confirm the single end-to-end
   transaction first (below), then extend to 5 orgs as its own step.

3. **Confirm one signed transaction end-to-end** — this is what's already
   been done and confirmed working:

   ```bash
   export FABRIC_SAMPLES_DIR=$HOME/fabric-samples   # or wherever bootstrap.sh put it
   cd workers/chain_worker
   python3 -c "
   from fabric_client import FabricClient
   client = FabricClient(channel_name='legadoc-channel')
   print('SUBMIT:', client.submit_hash(doc_id='test-doc-1', doc_hash='deadbeef', org_id='org1'))
   print('GET:', client.get_hash(doc_id='test-doc-1'))
   print('VERIFY (correct):', client.verify_hash(doc_id='test-doc-1', hash_to_check='deadbeef'))
   print('VERIFY (tampered):', client.verify_hash(doc_id='test-doc-1', hash_to_check='wrong'))
   "
   ```

   No connection profile or `fabric-sdk-py` needed anymore — `fabric_client.py`
   shells out to the `peer` CLI directly (see its docstring for why). This
   reads test-network's crypto material straight from `FABRIC_SAMPLES_DIR`,
   hardcoded to Org1 submitting / Org1+Org2 endorsing, matching the default
   2-org network above.

## Never commit here

Local dev crypto material (MSP identities, private keys) belongs in this
folder for local testing only, and is gitignored — see the repo's
`.gitignore`. A real production identity should never touch this
repository at all, local or otherwise; production keys come from the
secrets manager named in SYSTEM_DESIGN.md's "Key management" section.
