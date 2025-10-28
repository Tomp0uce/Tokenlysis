from __future__ import annotations

import dramatiq
from dramatiq.brokers.stub import StubBroker

broker = StubBroker()
dramatiq.set_broker(broker)
