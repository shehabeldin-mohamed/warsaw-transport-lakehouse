"""Command line entry point: `ztm-ingest --type 1 --interval 30`."""

from __future__ import annotations

import argparse
import logging
import signal
import time

from ztm_ingest.client import ApiError, ZtmClient
from ztm_ingest.config import Settings
from ztm_ingest.ingest import run_once
from ztm_ingest.storage import make_writer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll ZTM vehicle positions into bronze.")
    parser.add_argument("--type", type=int, nargs="+", default=[1, 2], help="1=bus, 2=tram")
    parser.add_argument("--interval", type=int, default=0, help="seconds between polls; 0 = once")
    args = parser.parse_args(argv)

    settings = Settings()  # values come from the environment
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("ztm_ingest")

    client = ZtmClient(settings)
    writer = make_writer(settings)

    stop = False

    def _handle(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    while not stop:
        started = time.monotonic()
        for vtype in args.type:
            try:
                run_once(settings, client, writer, vtype)
            except ApiError as exc:
                # One failed poll must not kill a long-running collector.
                log.error("poll failed: %s", exc, extra={"vehicle_type": vtype})
        if args.interval <= 0:
            break
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval - elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
