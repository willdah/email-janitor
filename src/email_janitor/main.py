import asyncio
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from email_janitor.agents.root_agent import create_root_agent
from email_janitor.config import AppConfig, DatabaseConfig
from email_janitor.database import DatabaseService

# Load environment variables before instantiating settings
load_dotenv()


async def main():
    """Main event loop for the email janitor agent."""
    config = AppConfig()
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)

    root_agent = create_root_agent(persist_run=db.persist_run)
    app = App(name=config.app_name, root_agent=root_agent)

    start_message = types.Content(parts=[types.Part(text="Begin the email janitor process.")])
    runner = InMemoryRunner(app_name=config.app_name, app=app)

    # Continuously run the agent until the user exits
    try:
        while True:
            try:
                run_id = str(uuid.uuid4())
                started_at = datetime.now(UTC).isoformat()

                # Create a new session per iteration with run metadata
                session = await runner.session_service.create_session(
                    app_name=config.app_name,
                    user_id=config.user_id,
                    state={"run_id": run_id, "run_started_at": started_at},
                )

                # Run the full agent pipeline
                async for event in runner.run_async(
                    user_id=config.user_id,
                    session_id=session.id,
                    new_message=start_message,
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                print(f"[{event.author}]: {part.text}")

                # Wait before running again
                print(f"\nWaiting {config.poll_interval} seconds before next run...\n")
                await asyncio.sleep(config.poll_interval)

            except KeyboardInterrupt:
                print("\nShutting down...")
                break
            except Exception as e:
                print(f"An error occurred: {e}")
                await asyncio.sleep(config.poll_interval)
    finally:
        await db.close()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
