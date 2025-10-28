from __future__ import annotations

import logging

import dramatiq

logger = logging.getLogger(__name__)


@dramatiq.actor
def recalculate_scores() -> None:
    logger.info("Recalculating thematic scores")
