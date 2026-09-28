from .models import Config


def run(config: Config | None = None) -> str:
    cfg = config or Config()
    return f"running with {cfg.name}"
