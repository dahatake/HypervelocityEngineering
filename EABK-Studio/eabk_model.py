"""Read-only model helpers used by the Studio server."""
from pathlib import Path
from studio import model

def load(repo: Path):
    return model(repo)
