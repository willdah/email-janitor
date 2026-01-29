from .sub_agents.email_collector_agent import email_collector_agent
from .sub_agents.email_labeler_agent import email_labeler_agent
from .sub_agents.email_loop_agent import email_loop_agent
from .sub_agents.email_classifier_agent import EmailClassifierAgent
from .config import ClassificationConfig
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.apps import App


# Create the email classifier agent
email_classifier_config = ClassificationConfig()
email_classifier_agent = EmailClassifierAgent(config=email_classifier_config)

# Create the classification loop agent (wraps EmailClassifierAgent in a loop)
email_classifier_loop_agent = LoopAgent(
    name="EmailClassifierLoopAgent",
    description="A loop agent that classifies emails one at a time.",
    sub_agents=[email_classifier_agent],
    max_iterations=100,
)

# Create the root agent: EmailCollectorAgent -> EmailLoopAgent -> [EmailClassificationLoop -> EmailClassifierAgent] -> EmailLabelerAgent
root_agent = SequentialAgent(
    name="EmailJanitor",
    description="A root agent that orchestrates the email janitor process: collects emails, classifies them in a loop, then processes all classifications.",
    sub_agents=[
        email_collector_agent,  # Step 1: Collect all unread emails
        email_loop_agent,  # Step 2: Initialize loop state (current_email_index)
        email_classifier_loop_agent,  # Step 3: Loop that classifies emails one at a time (contains EmailClassifierAgent)
        # email_labeler_agent,  # Step 4: Process all classified emails
    ],
)

app = App(name="email_janitor", root_agent=root_agent)
