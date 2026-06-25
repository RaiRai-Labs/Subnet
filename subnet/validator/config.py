"""Neuron configuration.

bittensor's ``Config(parser)`` (v10) does not reliably apply CLI overrides for
its own sections, so we parse a single argparse parser ourselves and flatten the
dotted dests (e.g. ``wallet.name``) into a nested ``bt.Config`` — which
`bt.Wallet` / `bt.Subtensor` / `bt.Axon` accept directly.
"""

import argparse

import bittensor as bt


def add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--netuid", type=int, default=1, help="Subnet netuid.")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run offline with a mock metagraph and mock miners (no chain).",
    )
    parser.add_argument(
        "--neuron.forward_interval",
        type=float,
        default=5.0,
        help="Seconds to wait between forward passes.",
    )
    parser.add_argument(
        "--neuron.epoch_length",
        type=int,
        default=10,
        help="Number of forward passes between weight settings.",
    )
    parser.add_argument(
        "--neuron.moving_average_alpha",
        type=float,
        default=0.2,
        help="EMA weight for new rewards when updating miner scores.",
    )
    parser.add_argument(
        "--neuron.rank_window",
        type=int,
        default=10,
        help="Rounds of per-challenge rank history to average for standings.",
    )
    parser.add_argument(
        "--neuron.persist_ranks",
        action="store_true",
        default=False,
        help="Persist rolling rank history to Postgres (requires DATABASE_URL).",
    )
    # --- Anti-gaming (Phase 4) ---
    parser.add_argument(
        "--neuron.allowed_absence",
        type=int,
        default=3,
        help="Consecutive no-shows before a miner's rank history is dropped.",
    )
    parser.add_argument(
        "--neuron.collusion_threshold",
        type=float,
        default=0.02,
        help="Mean abs prediction diff at/below which two miners are deemed colluding.",
    )
    parser.add_argument(
        "--blacklist.min_stake",
        type=float,
        default=0.0,
        help="Miner: reject axon requests from hotkeys staking below this (TAO).",
    )
    parser.add_argument(
        "--blacklist.validator_permit",
        action="store_true",
        default=False,
        help="Miner: only serve requesters that hold a validator permit.",
    )


def _flatten_into_config(namespace: argparse.Namespace) -> bt.Config:
    """Turn a flat namespace with dotted keys into a nested bt.Config."""
    config = bt.Config()
    for key, value in vars(namespace).items():
        parts = key.split(".")
        node = config
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = bt.Config()
            node = node[part]
        node[parts[-1]] = value
    return config


def get_config() -> bt.Config:
    parser = argparse.ArgumentParser()
    add_args(parser)
    bt.Wallet.add_args(parser)
    bt.Subtensor.add_args(parser)
    bt.Axon.add_args(parser)
    bt.logging.add_args(parser)
    args, _ = parser.parse_known_args()
    return _flatten_into_config(args)
