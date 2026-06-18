import logging
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def is_railway_environment(env: Mapping[str, str] | None = None) -> bool:
    values = env or os.environ
    return any(key.startswith("RAILWAY_") for key in values)


def should_start_bot(env: Mapping[str, str] | None = None) -> bool:
    values = env or os.environ
    explicit = values.get("FORTUNA_START_BOT_WITH_API")
    if explicit is not None:
        normalized = explicit.strip().casefold()
        if normalized in FALSE_VALUES:
            return False
        if normalized in TRUE_VALUES:
            return bool(values.get("TELEGRAM_BOT_TOKEN")) and bool(values.get("REDIS_URL"))
    return bool(values.get("TELEGRAM_BOT_TOKEN")) and bool(values.get("REDIS_URL"))


def api_command(env: Mapping[str, str] | None = None) -> list[str]:
    values = env or os.environ
    port = values.get("PORT") or "8000"
    return [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port]


def bot_command() -> list[str]:
    return [sys.executable, "-m", "app.bot.runner"]


def _terminate(processes: Sequence[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 15
    for process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            process.kill()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    processes: list[tuple[str, subprocess.Popen]] = []

    api = subprocess.Popen(api_command())
    processes.append(("api", api))

    if should_start_bot():
        logger.info("Starting Fortuna OS API and Telegram bot worker in this Railway service")
        bot = subprocess.Popen(bot_command())
        processes.append(("bot", bot))
    else:
        logger.info("Starting Fortuna OS API only")

    stopping = False

    def handle_signal(signum, _frame) -> None:
        nonlocal stopping
        stopping = True
        logger.info("Received signal %s; stopping Fortuna OS runtime", signum)
        _terminate([process for _name, process in processes])

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while not stopping:
        for name, process in processes:
            return_code = process.poll()
            if return_code is not None:
                if name == "bot":
                    logger.error("Fortuna OS bot worker exited with code %s", return_code)
                else:
                    logger.error("Fortuna OS API exited with code %s", return_code)
                _terminate([other for other_name, other in processes if other_name != name])
                return return_code if return_code != 0 else 1
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
