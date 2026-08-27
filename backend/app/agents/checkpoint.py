from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import Settings, get_settings


def _configure_windows_event_loop() -> None:
    """Use the psycopg-compatible event loop for the Windows CLI entry point."""
    if sys.platform != "win32":
        return
    policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_factory is not None:
        asyncio.set_event_loop_policy(policy_factory())


def _checkpoint_dsn(settings: Settings) -> str:
    value = settings.agent_checkpoint_database_url.get_secret_value().strip()
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def agent_checkpointer(
    settings: Settings | None = None,
) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    config = settings or get_settings()
    dsn = _checkpoint_dsn(config)
    if not dsn:
        if config.environment == "production":
            raise RuntimeError("AGENT_CHECKPOINT_DATABASE_URL is required in production")
        yield InMemorySaver()
        return
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        yield saver


async def setup_checkpoint_schema(settings: Settings | None = None) -> bool:
    config = settings or get_settings()
    dsn = _checkpoint_dsn(config)
    if not dsn:
        if config.environment == "production":
            raise RuntimeError("AGENT_CHECKPOINT_DATABASE_URL is required in production")
        return False
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage LangGraph checkpoint infrastructure")
    parser.add_argument("command", choices=["setup"])
    args = parser.parse_args()
    if args.command == "setup":
        _configure_windows_event_loop()
        asyncio.run(setup_checkpoint_schema())


if __name__ == "__main__":
    main()
