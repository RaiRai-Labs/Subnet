"""Local end-to-end smoke test against a running subtensor localnet.

Runs the miner and validator neurons together in one process (each on its own
background thread, real axon/dendrite over localhost) against netuid 2 on
ws://127.0.0.1:9944. Validator poses tasks, queries the miner over the chain's
axon, scores it, and sets weights.

Usage:
    uv run python scripts/localnet_e2e.py [seconds]
"""

import sys
import time

import bittensor as bt

from neurons.miner import Miner
from neurons.validator import Validator
from subnet.validator.config import get_config

NETUID = 2
ENDPOINT_ARGS = ["--netuid", str(NETUID), "--subtensor.network", "local"]


def cfg(extra: list[str]) -> bt.Config:
    sys.argv = ["e2e", *ENDPOINT_ARGS, *extra]
    return get_config()


def main() -> None:
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    bt.logging.enable_info()

    miner_cfg = cfg([
        "--wallet.name", "miner", "--wallet.hotkey", "default",
        "--axon.ip", "127.0.0.1", "--axon.external_ip", "127.0.0.1",
        "--axon.port", "8191",
    ])
    val_cfg = cfg([
        "--wallet.name", "validator", "--wallet.hotkey", "default",
        "--neuron.forward_interval", "3", "--neuron.epoch_length", "3",
    ])

    miner = Miner(config=miner_cfg)
    with miner:
        # Wait for the miner's axon to be registered + serving on chain.
        print(">>> waiting for miner axon to serve on chain...")
        for _ in range(40):
            mg = miner.subtensor.metagraph(NETUID)
            if mg.axons[miner.uid].is_serving:
                ax = mg.axons[miner.uid]
                print(f">>> miner serving: uid {miner.uid} @ {ax.ip}:{ax.port}")
                break
            time.sleep(2)
        else:
            print("!!! miner never reported serving; continuing anyway")

        validator = Validator(config=val_cfg)
        validator.metagraph = validator.subtensor.metagraph(NETUID)
        validator.scores = validator.scores  # already sized to metagraph.n
        with validator:
            print(f">>> running validator for {duration}s...")
            time.sleep(duration)

        # Report on-chain weights set by the validator.
        print(">>> final on-chain weights for netuid", NETUID)
        mg = validator.subtensor.metagraph(NETUID)
        for uid in mg.uids.tolist():
            print(f"    uid {uid}: weight={float(mg.weights[uid].sum()) if hasattr(mg,'weights') else 'n/a'} "
                  f"stake={float(mg.S[uid]):.2f}")
        print(">>> validator local scores:", [round(s, 3) for s in validator.scores.tolist()])


if __name__ == "__main__":
    main()
