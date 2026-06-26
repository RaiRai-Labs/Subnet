"""RaiRai Subnet validator neuron entry point.

Offline dev run:
    uv run python -m neurons.validator --mock

Live run (later):
    uv run python -m neurons.validator \
        --netuid <id> --subtensor.network <net> \
        --wallet.name <w> --wallet.hotkey <h>
"""

import os
import time

import bittensor as bt

from subnet.base.validator import BaseValidatorNeuron
from subnet.observability import Alerter, configure_logging, write_heartbeat
from subnet.validator.forward import forward


class Validator(BaseValidatorNeuron):
    def forward(self) -> None:
        forward(self)


def main() -> None:
    configure_logging()
    alerter = Alerter()
    heartbeat = os.getenv("RAIRAI_HEARTBEAT_FILE")
    with Validator() as validator:
        alerter.send(f"validator started (uid {validator.uid})")
        try:
            while not validator.should_exit:
                bt.logging.info(
                    f"Validator alive | step {validator.step} | "
                    f"scores={validator.scores.round(3).tolist()}"
                )
                if heartbeat:
                    write_heartbeat(
                        heartbeat,
                        role="validator",
                        uid=validator.uid,
                        step=validator.step,
                        scores=validator.scores.round(3).tolist(),
                    )
                time.sleep(15)
        except Exception as exc:  # noqa: BLE001 - surface fatal errors as an alert
            alerter.send(f"validator stopped: {exc}", level="error")
            raise


if __name__ == "__main__":
    main()
