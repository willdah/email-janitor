from .sub_agents.email_collector import email_collector
from google.adk.agents.sequential_agent import SequentialAgent


root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process.",
    sub_agents=[email_collector],
)