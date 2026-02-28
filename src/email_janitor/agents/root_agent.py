from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.sequential_agent import SequentialAgent

from ..callbacks.callbacks import initialize_loop_state_callback
from ..config import EmailClassifierConfig, EmailCollectorConfig, EmailLabelerConfig
from ..database import PersistRunFn
from .email_classifier_agent import create_email_classifier_agent
from .email_collector_agent import create_email_collector_agent
from .email_labeler_agent import create_email_labeler_agent


def create_root_agent(
    collector_config: EmailCollectorConfig | None = None,
    classifier_config: EmailClassifierConfig | None = None,
    labeler_config: EmailLabelerConfig | None = None,
    persist_run: PersistRunFn | None = None,
) -> SequentialAgent:
    """
    Factory function that wires all agents into the root SequentialAgent.

    Args:
        collector_config: Configuration for the email collector agent
        classifier_config: Configuration for the email classifier agent
        labeler_config: Configuration for the email labeler agent
        persist_run: Optional async callable for persisting run data to a database

    Returns:
        A fully configured SequentialAgent ready to run the email janitor pipeline
    """
    email_collector = create_email_collector_agent(config=collector_config or EmailCollectorConfig())

    email_classifier = create_email_classifier_agent(
        config=classifier_config or EmailClassifierConfig(),
    )

    email_classifier_loop = LoopAgent(
        name="EmailClassifierLoopAgent",
        description="A loop agent that classifies emails one at a time.",
        sub_agents=[email_classifier],
        max_iterations=100,
        before_agent_callback=initialize_loop_state_callback,
    )

    email_labeler = create_email_labeler_agent(config=labeler_config or EmailLabelerConfig(), persist_run=persist_run)

    return SequentialAgent(
        name="EmailJanitor",
        description=(
            "A root agent that orchestrates the email janitor process: collects emails,"
            " classifies them in a loop, then processes all classifications."
        ),
        sub_agents=[email_collector, email_classifier_loop, email_labeler],
    )


root_agent = create_root_agent()
