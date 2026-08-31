import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure a reusable default for application logs."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
