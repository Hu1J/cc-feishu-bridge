"""CLI entry point."""
from __future__ import annotations

import argparse
import logging

from src.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Claude Code Feishu Bridge")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config(args.config)
    logging.info("Config loaded, starting bridge service...")
    # TODO: start services


if __name__ == "__main__":
    main()
