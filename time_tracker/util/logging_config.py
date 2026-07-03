import logging

from time_tracker.paths import log_path


def configure_logging() -> None:
    logging.basicConfig(
        filename=log_path(),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
