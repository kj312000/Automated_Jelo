"""
Structured logging — structlog routed through stdlib with rotating file output.
Import and call setup_logging() at the very top of main.py, before local imports.
"""
import logging
import logging.handlers
import os

import structlog


def setup_logging(log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)

    # Processors shared by both structlog and foreign (stdlib) log records
    pre_chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # File formatter: key=value for easy grep
    file_fmt = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.KeyValueRenderer(
                key_order=["timestamp", "level", "logger", "event"]
            ),
        ],
        foreign_pre_chain=pre_chain,
    )

    # Console formatter: plain readable text (no ANSI — works on Windows)
    console_fmt = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        foreign_pre_chain=pre_chain,
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(console_fmt)

    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "btc_mst.log"),
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_fmt)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(ch)
    root.addHandler(fh)
    root.setLevel(logging.DEBUG)

    # Silence chatty third-party loggers (still written to file at WARNING+)
    for noisy in ("websockets", "httpx", "asyncio", "urllib3", "python_binance",
                  "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
