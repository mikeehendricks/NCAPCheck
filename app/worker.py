"""Separate APScheduler worker; run with ``python -m app.worker``."""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from . import create_app
from .checks import run_due_checks

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ncapcheck.worker")


def main() -> None:
    app = create_app()
    interval = max(1, int(app.config.get("SCHEDULER_INTERVAL_MINUTES", 10)))

    def tick() -> None:
        with app.app_context():
            try:
                result = run_due_checks()
                logger.info("Review scheduler completed: %s vehicle(s), %s provider task(s)", result["vehicles_scheduled"], result["provider_tasks"])
            except Exception:
                logger.exception("Review scheduler cycle failed")
                from . import db
                db.session.rollback()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(tick, "interval", minutes=interval, id="due-reviews", max_instances=1, coalesce=True, misfire_grace_time=120)
    logger.info("Worker started; polling review queue every %s minute(s).", interval)
    tick()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopping.")


if __name__ == "__main__":
    main()
