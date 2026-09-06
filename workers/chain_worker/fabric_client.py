"""
The one place this worker actually talks to Hyperledger Fabric.

REWRITTEN to shell out to the `peer` CLI via subprocess instead of using
fabric-sdk-py (hfc). Why: hfc is a community SDK with no meaningful recent
maintenance, and installing it hit a real, confirmed cascade of
version-incompatible transitive dependencies — not assumed, actually
tried:
  - pysha3 (a hard-pinned dependency) has C code that does not compile on
    Python 3.10+ (CPython's Py_TYPE macro stopped being assignable)
  - hfc's own bundled *_pb2.py files were generated with an old protoc and
    reject any recent protobuf runtime
  - hfc's pinned requests/urllib3 versions no longer agree with each other
    (urllib3's bundled six-compat shim is gone in the versions that
    actually resolve)
Every one of those is a dead end in the *library*, not in this network or
this chaincode. The peer CLI is what Hyperledger's own tooling uses
internally, and it's exactly what fabric-network/README.md's manual smoke
test already proved works end-to-end against a real, live 2-org network —
this class just wraps that same, already-working command shape in Python
instead of continuing to fight an abandoned library's decade-old
dependencies. If a future contributor wants to revisit hfc once it's
better maintained (or switch to the Node/Java SDK, which are actively
maintained), this class's public methods (submit_hash/get_hash/verify_hash)
are the seam to swap behind — nothing else in this codebase needs to change.

Assumes the standard fabric-samples test-network layout (see
fabric-network/README.md) — override FABRIC_SAMPLES_DIR if yours lives
somewhere else. Hardcoded to the 2-org default network (Org1 submits,
Org1+Org2 endorse) — extending to the design's full 5-org topology is
separate work (see SYSTEM_DESIGN.md and the Risk Dossier), not done here.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class FabricSubmissionError(Exception):
    """Raised for any failure invoking or querying the chaincode — worker.py
    catches this one exception type rather than needing to know every way
    the `peer` CLI can fail."""


def _test_network_dir() -> Path:
    samples_dir = Path(os.environ.get("FABRIC_SAMPLES_DIR", str(Path.home() / "fabric-samples")))
    return samples_dir / "test-network"


class FabricClient:
    def __init__(
        self,
        channel_name: str,
        chaincode_name: str = "hashledger",
        org: str = "org1",
        peer_bin: Optional[str] = None,
    ):
        self.channel_name = channel_name
        self.chaincode_name = chaincode_name
        self.tn = _test_network_dir()
        if not self.tn.exists():
            raise FabricSubmissionError(
                f"test-network not found at {self.tn} — set FABRIC_SAMPLES_DIR, "
                "or run the bootstrap + setup-test-network.sh steps in "
                "fabric-network/README.md first."
            )

        # peer binary: prefer an explicit path so this works even when called
        # from a process (e.g. a Celery worker) that didn't inherit the
        # interactive shell's PATH export.
        self.peer_bin = peer_bin or str(self.tn.parent / "bin" / "peer")

        org_domain = f"{org}.example.com"
        org_msp = f"{org.capitalize()}MSP"
        peer_port = "7051" if org == "org1" else "9051"

        self._env = dict(os.environ)
        self._env.update({
            "FABRIC_CFG_PATH": str(self.tn / ".." / "config"),
            "CORE_PEER_TLS_ENABLED": "true",
            "CORE_PEER_LOCALMSPID": org_msp,
            "CORE_PEER_TLS_ROOTCERT_FILE": str(
                self.tn / "organizations/peerOrganizations" / org_domain / "peers" / f"peer0.{org_domain}" / "tls/ca.crt"
            ),
            "CORE_PEER_MSPCONFIGPATH": str(
                self.tn / "organizations/peerOrganizations" / org_domain / "users" / f"Admin@{org_domain}" / "msp"
            ),
            "CORE_PEER_ADDRESS": f"localhost:{peer_port}",
        })

        self._orderer_ca = str(
            self.tn / "organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
        )
        self._org1_tls = str(
            self.tn / "organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
        )
        self._org2_tls = str(
            self.tn / "organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
        )

    def _run(self, args: list, timeout: int = 60) -> str:
        try:
            result = subprocess.run(
                [self.peer_bin, *args],
                env=self._env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise FabricSubmissionError(
                f"`peer` binary not found at {self.peer_bin} — check FABRIC_SAMPLES_DIR / bootstrap.sh."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise FabricSubmissionError(f"peer command timed out after {timeout}s") from e

        # `peer` writes its actual result to stderr (INFO-level logging), not
        # stdout — capture both, since the caller needs to parse the result
        # either way.
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise FabricSubmissionError(f"peer command failed (exit {result.returncode}): {output.strip()}")
        return output

    def submit_hash(self, doc_id: str, doc_hash: str, org_id: str) -> dict:
        """RecordHash — endorsed by both Org1 and Org2, ordered, committed."""
        args_json = json.dumps({"function": "RecordHash", "Args": [doc_id, doc_hash, org_id]})
        output = self._run([
            "chaincode", "invoke",
            "-o", "localhost:7050",
            "--ordererTLSHostnameOverride", "orderer.example.com",
            "--tls",
            "--cafile", self._orderer_ca,
            "-C", self.channel_name,
            "-n", self.chaincode_name,
            "--peerAddresses", "localhost:7051",
            "--tlsRootCertFiles", self._org1_tls,
            "--peerAddresses", "localhost:9051",
            "--tlsRootCertFiles", self._org2_tls,
            "-c", args_json,
            "--waitForEvent",
        ], timeout=90)
        if "successful" not in output.lower() and "status:200" not in output:
            raise FabricSubmissionError(f"RecordHash did not report success: {output.strip()}")
        return {"raw_output": output.strip()}

    def get_hash(self, doc_id: str) -> dict:
        """GetHash — a query, no endorsement/ordering needed."""
        args_json = json.dumps({"function": "GetHash", "Args": [doc_id]})
        output = self._run(["chaincode", "query", "-C", self.channel_name, "-n", self.chaincode_name, "-c", args_json])
        try:
            return json.loads(output.strip())
        except json.JSONDecodeError:
            return {"raw_output": output.strip()}

    def verify_hash(self, doc_id: str, hash_to_check: str) -> bool:
        """VerifyHash — the live tamper-check: does this hash still match what's on the ledger?"""
        args_json = json.dumps({"function": "VerifyHash", "Args": [doc_id, hash_to_check]})
        output = self._run(["chaincode", "query", "-C", self.channel_name, "-n", self.chaincode_name, "-c", args_json])
        return output.strip().lower() == "true"
