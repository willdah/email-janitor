from .sub_agents.email_collector_agent import email_collector_agent
from .sub_agents.email_labeler_agent import email_labeler_agent
from .sub_agents.email_classifier_agent import EmailClassifierAgent
from .config import ClassificationConfig
from .callbacks import (
    initialize_loop_state_callback,
    accumulate_classifications_callback,
)
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.apps import App


# Create the email classifier agent with after_agent_callback for accumulation
# The callback runs after each classification to accumulate results
email_classifier_config = ClassificationConfig()
email_classifier_agent = EmailClassifierAgent(
    config=email_classifier_config,
    after_agent_callback=accumulate_classifications_callback,
)

# Create the classification loop agent (wraps EmailClassifierAgent in a loop)
# - before_agent_callback: initializes loop state (replaces EmailLoopAgent)
email_classifier_loop_agent = LoopAgent(
    name="EmailClassifierLoopAgent",
    description="A loop agent that classifies emails one at a time.",
    sub_agents=[email_classifier_agent],
    max_iterations=100,
    before_agent_callback=initialize_loop_state_callback,
)

# Create the root agent: EmailCollectorAgent -> [EmailClassificationLoop -> EmailClassifierAgent] -> EmailLabelerAgent
# Note: EmailLoopAgent has been replaced by before_agent_callback on the loop agent
root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process: collects emails, classifies them in a loop, then processes all classifications.",
    sub_agents=[
        email_collector_agent,  # Step 1: Collect all unread emails
        email_classifier_loop_agent,  # Step 2: Loop that classifies emails one at a time (with state init callback)
        email_labeler_agent,  # Step 3: Process all classified emails
    ],
)

app = App(name="email_janitor", root_agent=root_agent)
