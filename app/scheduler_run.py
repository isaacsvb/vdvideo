"""Run any due scheduled jobs once, then exit.

Useful for driving the scheduler from an external cron / systemd timer without
keeping the API server running:

    python -m app.scheduler_run

It executes every job whose time has arrived (and hasn't run yet), marking each
done in storage/schedule.json.
"""
from __future__ import annotations

import sys

from app import scheduler


def main() -> int:
    ran = scheduler.run_due_jobs()
    if ran:
        print(f"Ran {len(ran)} due job(s): {', '.join(ran)}")
    else:
        print("No due jobs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
