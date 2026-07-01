// PM2 ecosystem — declarative bring-up for a RaiRai box (Phase 5 ops).
//
// One command instead of the start_*.sh scripts. Pick the role with --only:
//
//   pm2 start ecosystem.config.js --only rairai-validator,rairai-updater
//   pm2 start ecosystem.config.js --only rairai-miner,rairai-updater
//   pm2 save && pm2 startup        # resurrect on reboot
//
// Config comes from .env (same keys the start scripts read): NETUID,
// SUBTENSOR_NETWORK, WALLET_NAME, WALLET_HOTKEY, AXON_PORT, AXON_EXTERNAL_IP,
// plus DATABASE_URL / SH_* / RAIRAI_* which the neuron inherits via `env`.
// A real process-env var overrides the .env value of the same name.
//
// The updater tracks rairai-validator by default; on a miner box set
// UPDATER_PM2_NAME=rairai-miner (or edit --pm2-name below).

const fs = require('fs');
const path = require('path');

// Tiny dependency-free .env parser (avoids requiring the dotenv npm package).
function loadEnv(file) {
  const out = {};
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch (_) {
    return out; // no .env on this box — fall back to the process environment
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

// Real environment wins over .env so `VAR=x pm2 start ...` still overrides.
const env = { ...loadEnv(path.join(__dirname, '.env')), ...process.env };

const pair = (flag, key) => (env[key] ? [flag, env[key]] : []);

const neuronArgs = (module, walletNameKey, walletHotkeyKey, extra) =>
  [
    'run', 'python', '-m', module,
    ...pair('--netuid', 'NETUID'),
    ...pair('--subtensor.network', 'SUBTENSOR_NETWORK'),
    ...pair('--wallet.name', walletNameKey),
    ...pair('--wallet.hotkey', walletHotkeyKey),
    ...pair('--wallet.path', 'WALLET_PATH'),
    ...extra,
  ].join(' ');

const minerExtra = [
  ...pair('--axon.ip', 'AXON_IP'),
  ...pair('--axon.port', 'AXON_PORT'),
  ...pair('--axon.external_ip', 'AXON_EXTERNAL_IP'),
];

const common = {
  interpreter: 'none',     // `uv` is the executable, not a JS script
  cwd: __dirname,
  time: true,              // timestamp each log line
  autorestart: true,
  restart_delay: 5000,     // 5s backoff between crash restarts
  max_restarts: 50,
  env,                     // neuron inherits DATABASE_URL / SH_* / RAIRAI_*
};

module.exports = {
  apps: [
    {
      ...common,
      name: 'rairai-validator',
      script: 'uv',
      args: neuronArgs('neurons.validator', 'VALIDATOR_WALLET_NAME', 'VALIDATOR_WALLET_HOTKEY', ['--neuron.persist_ranks']),
    },
    {
      ...common,
      name: 'rairai-miner',
      script: 'uv',
      args: neuronArgs('neurons.miner', 'MINER_WALLET_NAME', 'MINER_WALLET_HOTKEY', minerExtra),
    },
    {
      ...common,
      name: 'rairai-api',
      script: 'uv',
      args: ['run', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', env.API_PORT || '8080'].join(' '),
    },
    {
      ...common,
      name: 'rairai-updater',
      script: 'scripts/run_neuron.py',
      interpreter: 'python3',
      args: [
        '--pm2-name', env.UPDATER_PM2_NAME || 'rairai-validator',
        '--branch', env.UPDATER_BRANCH || 'main',
        '--interval', env.UPDATER_INTERVAL || '300',
      ].join(' '),
    },
  ],
};
