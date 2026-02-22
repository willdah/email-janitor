import asyncio

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from email_janitor.agent import app

# Constants
APP_NAME = "Email-Janitor"
USER_ID = "email-janitor-user"
SESSION_ID = "email-janitor-session"

# Load environment variables
load_dotenv()


# Define the main function
async def main():
    """Main event loop for the email janitor agent."""
    start_message = types.Content(parts=[types.Part(text="Begin the email janitor process.")])
    runner = InMemoryRunner(app_name=APP_NAME, app=app)

    # Continuously run the agent until the user exits
    while True:
        try:
            # Create a new session per iteration
            session = await runner.session_service.create_session(
                app_name=APP_NAME,
                user_id=USER_ID,
            )

            # run_async returns an AsyncGenerator, so we need to iterate over events
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=start_message,
            ):
                # Process each event as it arrives
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            print(f"[{event.author}]: {part.text}")

            # Wait before running again
            print("\nWaiting 10 seconds before next run...\n")
            await asyncio.sleep(10)

        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            await asyncio.sleep(10)  # Wait before retrying


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
