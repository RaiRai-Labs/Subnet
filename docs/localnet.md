# Running against a local subtensor chain

End-to-end dev setup: a local Bittensor chain, a subnet, and the validator +
miner neurons talking over the chain (real axon/dendrite + on-chain weights).

## 1. Start a local subtensor (fast blocks)

```bash
docker run -d --name rairai_localnet -p 9944:9944 -p 9945:9945 \
  ghcr.io/opentensor/subtensor-localnet:latest
```

RPC is at `ws://127.0.0.1:9944` (network alias `local`). The dev account
`//Alice` is pre-funded with 1,000,000 TAO.

## 2. Wallets, funding, subnet, registration

`btcli` has no faucet anymore, so fund from `//Alice` via the SDK. Helper steps
(run with `uv run python - <<'PY' … PY`):

- Create coldkey+hotkey for `validator` and `miner` (`bt.Wallet(...).create_new_coldkey/hotkey(use_password=False)`).
- Transfer TAO from `//Alice` (`Balances.transfer_keep_alive`) to both coldkeys.
- `subtensor.register_subnet(wallet=validator_wallet)` → creates the subnet
  (lock cost 1,000 TAO); the owner hotkey is registered automatically. Our run
  produced **netuid 2**.
- `subtensor.burned_register(wallet=miner_wallet, netuid=2)` → registers the miner.

The owner/validator (uid 0) gets a `validator_permit` automatically on localnet,
so no staking is required to set weights. (Alpha staking is disabled until the
subnet is activated — `SubtokenDisabled`.)

## 3. Run the miner

The chain rejects loopback IPs (`Custom error 11 = InvalidIpAddress`), so
advertise the host's real IP (bind all interfaces):

```bash
uv run python -m neurons.miner \
  --netuid 2 --subtensor.network local \
  --wallet.name miner --wallet.hotkey default \
  --axon.ip 0.0.0.0 --axon.external_ip <HOST_IP> --axon.port 8191
```

Confirm it serves: the metagraph should show `uid 1: serving=True <HOST_IP>:8191`.

## 4. Run the validator

```bash
uv run python -m neurons.validator \
  --netuid 2 --subtensor.network local \
  --wallet.name validator --wallet.hotkey default \
  --neuron.forward_interval 3 --neuron.epoch_length 3
```

Each step it poses a task, queries the miner over the dendrite, scores by MAE
rank, and submits weights every `epoch_length` steps.

> The subnet has `commit_reveal_weights_enabled = True`, so `set_weights`
> succeeds (`success=True`) but stores an encrypted commit — the plaintext
> `Weights` storage stays empty until the reveal window. Activating emissions
> (`is_subnet_active = False`) needs a `start_call`; not required for this test.

## One-shot harness

`scripts/localnet_e2e.py` runs miner + validator together in one process
(separate subtensor connections per neuron) for a quick smoke test:

```bash
uv run python -m scripts.localnet_e2e 30
```

## Teardown

```bash
docker rm -f rairai_localnet
```
