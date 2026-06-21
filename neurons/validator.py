"""RaiRai Subnet validator neuron entry point.

Offline dev run:
    uv run python -m neurons.validator --mock

Live run (later):
    uv run python -m neurons.validator \
        --netuid <id> --subtensor.network <net> \
        --wallet.name <w> --wallet.hotkey <h>
"""

import time

import bittensor as bt

from subnet.base.validator import BaseValidatorNeuron
from subnet.validator.forward import forward


class Validator(BaseValidatorNeuron):
    def forward(self) -> None:
        forward(self)


def main() -> None:
    with Validator() as validator:
        while not validator.should_exit:
            bt.logging.info(
                f"Validator alive | step {validator.step} | "
                f"scores={validator.scores.round(3).tolist()}"
            )
            time.sleep(15)


if __name__ == "__main__":
    main()
