from .sub_agents.email_collector import email_collector
from .sub_agents.email_classifier import email_classifier
from .sub_agents.email_processor import email_processor
from .sub_agents.email_loop_coordinator import email_loop_coordinator
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.loop_agent import LoopAgent


# Create the email processing loop agent
# This loop processes one email at a time: EmailClassifier -> EmailProcessor
# max_iterations is set to 100 to handle reasonable email volumes
# The loop will exit early when all emails are processed (handled by EmailClassifier)
email_processing_loop = LoopAgent(
    name="EmailProcessingLoop",
    description="A loop agent that processes emails one at a time through classification and processing.",
    # sub_agents=[email_classifier],
    sub_agents=[email_classifier, email_processor],
    max_iterations=100,  # Reasonable upper limit; loop exits early when all emails processed
)


# Root agent: EmailCollector -> EmailLoopCoordinator -> EmailProcessingLoop
root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process: collects emails, then processes them one at a time in a loop.",
    sub_agents=[
        email_collector,           # Step 1: Collect all unread emails
        email_loop_coordinator,    # Step 2: Initialize loop state
        email_processing_loop,    # Step 3: Process emails one at a time
    ],
)