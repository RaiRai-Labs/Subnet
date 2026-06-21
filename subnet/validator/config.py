"""Validator configuration.

bittensor's ``Config`` (v10) only absorbs its own sections (wallet, subtensor,
axon, logging), so we build that for the chain-native pieces and attach our
custom fields (mock, netuid, neuron.*) onto the same object — which `bt.Wallet`
/ `bt.Subtensor` still accept.
"""

import argparse

import bittensor as bt


def _custom_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--netuid", type=int, default=1, help="Subnet netuid.")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run offline with a mock metagraph and mock miners (no chain).",
    )
    parser.add_argument(
        "--neuron.forward_interval",
        dest="forward_interval",
        type=float,
        default=5.0,
        help="Seconds to wait between forward passes.",
    )
    parser.add_argument(
        "--neuron.epoch_length",
        dest="epoch_length",
        type=int,
        default=10,
        help="Number of forward passes between weight settings.",
    )
    parser.add_argument(
        "--neuron.moving_average_alpha",
        dest="moving_average_alpha",
        type=float,
        default=0.2,
        help="EMA weight for new rewards when updating miner scores.",
    )
    return parser


def get_config() -> bt.Config:
    # Chain-native config (wallet / subtensor / axon / logging).
    bt_parser = argparse.ArgumentParser()
    bt.Wallet.add_args(bt_parser)
    bt.Subtensor.add_args(bt_parser)
    bt.Axon.add_args(bt_parser)
    bt.logging.add_args(bt_parser)
    config = bt.Config(bt_parser)

    # Our custom fields, parsed separately and attached.
    args, _ = _custom_parser().parse_known_args()
    config.netuid = args.netuid
    config.mock = args.mock

    neuron = bt.Config(argparse.ArgumentParser())
    neuron.forward_interval = args.forward_interval
    neuron.epoch_length = args.epoch_length
    neuron.moving_average_alpha = args.moving_average_alpha
    config.neuron = neuron

    return config
