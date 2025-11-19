from langchain.agents import create_agent
from langchain_groq import ChatGroq

from AI_vs_I.domain.memory.short_term_memory import ShortTermMemory
from AI_vs_I.domain.prompts.prompt_templates import system_prompt
from AI_vs_I.infrastructure.monitoring.logger import Logger

logger = Logger.get_logger("model")


class Model:
    name: str
    color: str
    model: ChatGroq
    _contexts: dict[str, ShortTermMemory]
    logger: Logger

    def __init__(self, color: str, model_name: str):
        self.model_name = model_name
        self.color = color
        self.model = self.start_model(color, model_name)
        self._contexts = {}
        self.logger = Logger.get_logger(f"model {model_name}")
        self.logger.info(f"Model {model_name} (Mr. {color}) initialized.")

    def get_context(self) -> ShortTermMemory:
        """
        Retrieve or create a ShortTermMemory for this model/color.

        Returns:
            ShortTermMemory: The conversation context.
        """
        if self.color not in self._contexts:
            self._contexts[self.color] = ShortTermMemory(model_name=self.model_name)
        return self._contexts[self.color]

    def start_model(self, color, model="llama-3.1-8b-instant"):
        """
        Initialize and return the model.

        Args:
            color (str): The color assigned to the LLM.
            model (str): The model name to use for the LLM. Defaults to "llama-3.1-8b-instant".

        Returns:
            model: The initialized model.

        Raises:
            Exception: For unexpected errors during initialization.
        """
        try:
            llm_model = ChatGroq(model=model, temperature=0.3, max_retries=2)

            agent = create_agent(
                model=llm_model,
                tools=[],
                system_prompt=system_prompt.format(agent_color=color),
            )
            return agent
        except Exception as e:
            logger.exception(f"Error initializing agent: {e}")
            raise Exception(f"Error initializing agent: {e}") from e
