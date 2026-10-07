"""DNSmith's hub."""

# Kept in step with `version` in dnsmith/config.yaml; tests/test_hub.py
# fails the moment the two disagree.
__version__ = "0.1.1"

# DynDNS2 asks every client to identify itself by name, version and contact,
# and No-IP answers "badagent" to clients that do not. A bare "DNSmith" says
# who is calling but not which release, which is the part a provider needs
# to block one broken version instead of every user.
USER_AGENT = f"DNSmith/{__version__} (+https://github.com/duczz/ha-dnsmith)"
