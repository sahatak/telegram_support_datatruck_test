import logging
import time

import schedule
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_INTERVAL_HOURS = 2


def _run_sync() -> None:
    try:
        from services.sync_articles import sync_articles
        sync_articles()
    except Exception:
        logger.exception("Sync job raised an unhandled exception — will retry at next interval")


if __name__ == "__main__":
    logger.info("Sync runner starting — interval: %d h", _INTERVAL_HOURS)

    # Run immediately on start, then on schedule
    _run_sync()

    schedule.every(_INTERVAL_HOURS).hours.do(_run_sync)

    while True:
        schedule.run_pending()
        time.sleep(60)
