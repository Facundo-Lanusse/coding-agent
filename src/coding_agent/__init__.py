"""Advanced coding-agent package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("coding-agent-advanced")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
