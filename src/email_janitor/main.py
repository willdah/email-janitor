import asyncio
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from email_janitor.agents.root_agent import create_root_agent
from email_janitor.config import AppConfig, DatabaseConfig
from email_janitor.corrections.db import get_corrections_for_few_shot
from email_janitor.database import DatabaseService
from email_janitor.observability import configure_logging, configure_tracing, get_logger

# Load environment variables before instantiating settings
load_dotenv()


async def main():
    """Main event loop for the email janitor agent."""
    configure_logging()
    configure_tracing()
    logger = get_logger(__name__)

    config = AppConfig()
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)

    root_agent = create_root_agent(persist_run=db.persist_run)
    app = App(name=config.app_name, root_agent=root_agent)

    start_message = types.Content(parts=[types.Part(text="Begin the email janitor process.")])
    runner = InMemoryRunner(app_name=config.app_name, app=app)

    logger.info(
        "pipeline_starting",
        extra={"app_name": config.app_name, "poll_interval": config.poll_interval},
    )

    consecutive_failures = 0
    max_backoff_factor = 32  # caps exponential growth at poll_interval * 32

    try:
        while True:
            run_id = "unset"
            try:
                run_id = str(uuid.uuid4())
                started_at = datetime.now(UTC).isoformat()

                few_shot_corrections = []
                if db_config.path.exists():
                    few_shot_corrections = get_corrections_for_few_shot(db_config.path)

                session = await runner.session_service.create_session(
                    app_name=config.app_name,
                    user_id=config.user_id,
                    state={
                        "run_id": run_id,
                        "run_started_at": started_at,
                        "few_shot_corrections": few_shot_corrections,
                    },
                )

                logger.info(
                    "run_start",
                    extra={
                        "run_id": run_id,
                        "session_id": session.id,
                        "few_shot_count": len(few_shot_corrections),
                    },
                )

                async for event in runner.run_async(
                    user_id=config.user_id,
                    session_id=session.id,
                    new_message=start_message,
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                logger.debug(
                                    "agent_event",
                                    extra={
                                        "run_id": run_id,
                                        "author": event.author,
                                        "text": part.text,
                                    },
                                )

                consecutive_failures = 0
                logger.info(
                    "run_complete",
                    extra={"run_id": run_id, "poll_interval": config.poll_interval},
                )
                await asyncio.sleep(config.poll_interval)

            except KeyboardInterrupt:
                logger.info("shutdown", extra={"run_id": run_id})
                break
            except Exception:
                consecutive_failures += 1
                backoff = config.poll_interval * min(
                    2 ** consecutive_failures, max_backoff_factor
                )
                logger.exception(
                    "pipeline_error",
                    extra={
                        "run_id": run_id,
                        "consecutive_failures": consecutive_failures,
                        "backoff_seconds": backoff,
                    },
                )
                await asyncio.sleep(backoff)
    finally:
        await db.close()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
