"""Verify that the runner can wake an asyncio loop across threads."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from contextlib import suppress
from threading import Event, Thread


def _run_loop(
    loop: asyncio.AbstractEventLoop,
    ready: Event,
    safety_timeout_seconds: float,
) -> None:
    """Run one event loop until the probe asks it to stop."""
    asyncio.set_event_loop(loop)
    loop.call_later(safety_timeout_seconds, loop.stop)
    ready.set()
    loop.run_forever()


def probe_runner(timeout_seconds: float) -> bool:
    """Return whether a background event loop receives a thread-safe callback."""
    loop = asyncio.new_event_loop()
    loop_ready = Event()
    callback_received = Event()
    thread = Thread(
        target=_run_loop,
        args=(loop, loop_ready, timeout_seconds),
        name="asyncio-runner-probe",
        daemon=True,
    )
    thread.start()

    if not loop_ready.wait(timeout_seconds):
        thread.join(timeout_seconds)
        if not thread.is_alive():
            loop.close()
        return False

    callback_succeeded = False
    try:
        loop.call_soon_threadsafe(callback_received.set)
    except OSError:
        pass
    else:
        callback_succeeded = callback_received.wait(timeout_seconds)
    if callback_succeeded:
        with suppress(OSError):
            loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout_seconds)
    if thread.is_alive():
        return False
    loop.close()
    return callback_succeeded


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bounded cross-thread event-loop probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    if probe_runner(args.timeout_seconds):
        print("Asyncio runner probe passed.")
        return 0

    print(
        "Asyncio runner probe failed: the runner could not wake a background event loop. "
        "Ensure local socket-pair communication is permitted before running Starlette TestClient.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
