"""RaiRai Subnet miner neuron entry point.

Live run against a local chain:
    uv run python -m neurons.miner \
        --netuid 2 --subtensor.chain_endpoint ws://127.0.0.1:9944 \
        --wallet.name miner --wallet.hotkey default \
        --axon.ip 127.0.0.1 --axon.external_ip 127.0.0.1 --axon.port 8191
"""

import os
import time

import bittensor as bt

from subnet.base.miner import BaseMinerNeuron
from subnet.observability import Alerter, configure_logging, write_heartbeat
from subnet.protocol import YieldPredictionSynapse


class Miner(BaseMinerNeuron):
    def predict(self, synapse: YieldPredictionSynapse) -> YieldPredictionSynapse:
        # Simple heuristic baseline: scale mean NDVI into a plausible yield.
        ndvi = synapse.ndvi or []
        mean_ndvi = sum(ndvi) / len(ndvi) if ndvi else 0.5
        synapse.expected_yield = round(3.0 + 3.0 * mean_ndvi, 2)
        synapse.confidence = 0.8
        bt.logging.info(
            f"Predicted {synapse.expected_yield} for {synapse.crop} "
            f"(mean_ndvi={mean_ndvi:.2f})"
        )
        return synapse


def main() -> None:
    configure_logging()
    alerter = Alerter()
    heartbeat = os.getenv("RAIRAI_HEARTBEAT_FILE")
    with Miner() as miner:
        alerter.send(f"miner started (uid {miner.uid})")
        try:
            while not miner.should_exit:
                bt.logging.info(f"Miner alive | uid {miner.uid} | step {miner.step}")
                if heartbeat:
                    write_heartbeat(
                        heartbeat, role="miner", uid=miner.uid, step=miner.step
                    )
                time.sleep(15)
        except Exception as exc:  # noqa: BLE001 - surface fatal errors as an alert
            alerter.send(f"miner stopped: {exc}", level="error")
            raise


if __name__ == "__main__":
    main()
