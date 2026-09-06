#!/usr/bin/env bash
# Brings up a local Fabric test network and deploys the hashledger chaincode.
# UNTESTED — written from the documented fabric-samples test-network CLI
# (this is the standard, well-documented path Hyperledger's own tutorials
# use, so confidence here is higher than in fabric_client.py's SDK calls,
# but it has not been run in the environment this was written in — no
# Docker was available). Read every step before trusting it blindly.
#
# Prerequisites: Docker running, and fabric-samples + the peer/configtxgen/
# cryptogen binaries already fetched — see fabric-network/README.md's
# bootstrap.sh step. This script does NOT fetch those for you.
set -euo pipefail

# Adjust if bootstrap.sh put fabric-samples somewhere else.
FABRIC_SAMPLES_DIR="${FABRIC_SAMPLES_DIR:-$HOME/fabric-samples}"
CHANNEL_NAME="legadoc-channel"
CHAINCODE_NAME="hashledger"
CHAINCODE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../chaincode/hashledger" && pwd)"

if [ ! -d "$FABRIC_SAMPLES_DIR/test-network" ]; then
  echo "fabric-samples not found at $FABRIC_SAMPLES_DIR — run the bootstrap.sh step in fabric-network/README.md first, or set FABRIC_SAMPLES_DIR." >&2
  exit 1
fi

cd "$FABRIC_SAMPLES_DIR/test-network"

echo "== Bringing up the test network and creating '$CHANNEL_NAME' =="
./network.sh up createChannel -c "$CHANNEL_NAME"

echo "== Deploying $CHAINCODE_NAME from $CHAINCODE_PATH =="
./network.sh deployCC -c "$CHANNEL_NAME" -ccn "$CHAINCODE_NAME" -ccp "$CHAINCODE_PATH" -ccl go

echo
echo "Network is up, channel '$CHANNEL_NAME' created, '$CHAINCODE_NAME' deployed."
echo "This is the DEFAULT 2-org network (Org1, Org2) — SYSTEM_DESIGN.md's"
echo "Container Diagram names 5 (Police/FSL/Hospital-Medical/Court/External-"
echo "Verifiers). Extending to 5 orgs is separate, real work — see"
echo "fabric-network/README.md. Confirm one signed transaction against this"
echo "2-org network first."
echo
echo "Next: generate a connection profile for the org you'll submit as, and"
echo "run the smoke-test snippet in fabric-network/README.md step 4."
