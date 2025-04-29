#!/usr/bin/env python3
"""
Entrypoint for x_violet agent. Run this script to start the bot.
"""
import logging
import colorlog  # For colorful logs

from xviolet.agent import Agent


def setup_logging():
    # Configure root logger with colorized output
    root = logging.getLogger()
    root.handlers.clear()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main():
    setup_logging()
    agent = Agent()
    agent.run()


if __name__ == "__main__":
    main()
