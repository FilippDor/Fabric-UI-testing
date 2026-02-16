import logging

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)


def log_to_console(message: str, verbose: bool = False) -> None:
    """
    Simple logging helper with verbose mode
    """
    if verbose:
        logger.debug(message)