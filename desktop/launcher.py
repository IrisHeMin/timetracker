"""Entry point shared by the portable GUI and its scheduled report action."""

import logging
import sys


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            from report import main
        else:
            from app import main
        main()
    except Exception:
        from core import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=DATA_DIR / "launcher.log", encoding="utf-8")
        logging.exception("DayLedger could not complete the requested operation")
        sys.exit(1)
