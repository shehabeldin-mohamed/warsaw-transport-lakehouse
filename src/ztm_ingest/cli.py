"""Command line entry point: `ztm-ingest --type 1 --interval 30`."""

from __future__ import annotations

import argparse
import logging
import signal
import time

from ztm_ingest.client import VEHICLE_TYPES, ApiError, ZtmClient
from ztm_ingest.config import Settings
from ztm_ingest.ingest import run_once
from ztm_ingest.logging_setup import configure_logging
from ztm_ingest.storage import BronzeWriter, make_writer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll ZTM vehicle positions into bronze.")
    parser.add_argument(
        "--type",
        type=int,
        nargs="+",
        default=[1, 2],
        choices=sorted(VEHICLE_TYPES),
        help="1=bus, 2=tram",
    )
    parser.add_argument("--interval", type=int, default=0, help="seconds between polls; 0 = once")
    args = parser.parse_args(argv)

    settings = Settings()  # values come from the environment
    configure_logging(settings.log_level)
    log = logging.getLogger("ztm_ingest")

    client = ZtmClient(settings)
    writer = make_writer(settings)

    stop = False

    def _handle(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    # Remember the previous handlers and put them back on exit, so calling main()
    # (e.g. from tests) doesn't leave Ctrl+C swallowed for the rest of the process.
    previous = {sig: signal.signal(sig, _handle) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while not stop:
            started = time.monotonic()
            failed = 0
            for vtype in args.type:
                if not _poll(log, settings, client, writer, vtype):
                    failed += 1
            if args.interval <= 0:
                # Single run: report failure through the exit code, so scripts notice.
                return 1 if failed else 0
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, args.interval - elapsed))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0


def _poll(
    log: logging.Logger, settings: Settings, client: ZtmClient, writer: BronzeWriter, vtype: int
) -> bool:
    """One poll that never raises. Returns False if it failed.

    The API has no history, so a crashed collector loses data for good: one failed
    poll must never stop the loop.
    """
    try:
        run_once(settings, client, writer, vtype)
    except ApiError as exc:
        # Expected failures (bad key, API down after retries): one line, no traceback.
        log.error("poll failed", extra={"vehicle_type": vtype, "error": str(exc)})
        return False
    except Exception:
        # Anything else (disk full, storage outage, a bug): keep collecting, but log the
        # full traceback so the cause can be found and fixed.
        log.exception("poll failed unexpectedly", extra={"vehicle_type": vtype})
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
