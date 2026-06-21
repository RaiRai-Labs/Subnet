"""RaiRai subnet neuron library."""

__version__ = "0.1.0"

# Integer spec version used as the weight-commit `version_key` so that a
# commit and its later reveal are matched by the chain.
_major, _minor, _patch = (int(p) for p in __version__.split("."))
__spec_version__ = 1000 * _major + 100 * _minor + 10 * _patch
