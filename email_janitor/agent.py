from .sub_agents.email_collector import email_collector
from .sub_agents.email_classifier import email_classifier
from .sub_agents.email_processor import email_processor
from google.adk.agents.sequential_agent import SequentialAgent


root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process.",
    # sub_agents=[email_collector, email_classifier, email_processor],
    sub_agents=[email_collector, email_classifier],
)