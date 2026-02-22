import asyncio

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from email_janitor.agent import root_agent
from email_janitor.config import AppConfig

# Load environment variables before instantiating settings
load_dotenv()

config = AppConfig()
app = App(name=config.app_name, root_agent=root_agent)


async def main():
    """Main event loop for the email janitor agent."""
    start_message = types.Content(parts=[types.Part(text="Begin the email janitor process.")])
    runner = InMemoryRunner(app_name=config.app_name, app=app)

    # Continuously run the agent until the user exits
    while True:
        try:
            # Create a new session per iteration
            session = await runner.session_service.create_session(
                app_name=config.app_name,
                user_id=config.user_id,
            )

            # run_async returns an AsyncGenerator, so we need to iterate over events
            async for event in runner.run_async(
                user_id=config.user_id,
                session_id=session.id,
                new_message=start_message,
            ):
                # Process each event as it arrives
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


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
