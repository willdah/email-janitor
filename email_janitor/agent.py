from .sub_agents.email_collector import email_collector
from .sub_agents.email_processor import email_processor
from .sub_agents.email_loop_coordinator import email_loop_coordinator
from .sub_agents.classification_coordinator import ClassificationCoordinator
from .config import ClassificationConfig
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.apps import App


# Load configuration from environment variables using Pydantic Settings
config = ClassificationConfig()

# Create the classification coordinator with config
coordinator = ClassificationCoordinator(config=config)

# Create the email classification loop agent
# This loop classifies emails one at a time with critic review: ClassificationCoordinator
# max_iterations is set to 100 to handle reasonable email volumes
# The loop will exit early when all emails are processed (handled by ClassificationCoordinator)
email_classification_loop = LoopAgent(
    name="EmailClassificationLoop",
    description="A loop agent that classifies emails with critic review and refinement.",
    sub_agents=[coordinator],
    max_iterations=100,
)


# Root agent: EmailCollector -> EmailLoopCoordinator -> EmailClassificationLoop -> EmailProcessor
root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process: collects emails, classifies them in a loop, then processes all classifications.",
    sub_agents=[
        email_collector,  # Step 1: Collect all unread emails
        email_loop_coordinator,  # Step 2: Initialize loop state
        email_classification_loop,  # Step 3: Classify emails one at a time
        email_processor,  # Step 4: Process all classified emails
    ],
)

app = App(name="email_janitor", root_agent=root_agent)
