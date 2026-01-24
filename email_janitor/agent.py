from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool
from .gmail_client import get_unread_emails


root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="A helpful assistant for user questions.",
    instruction="Answer user questions to the best of your knowledge",
    tools=[FunctionTool(get_unread_emails)],
)
