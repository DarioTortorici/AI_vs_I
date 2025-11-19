from AI_vs_I.infrastructure.monitoring.logger import Logger

# Replace direct logging with centralized logger
logger = Logger.get_logger(__name__)


class ShortTermMemory:
    def __init__(self, model_name, max_size=10):
        """
        Initialize the ShortTermMemory with a maximum size.

        Args:
            max_size (int): Maximum number of conversations to retain in memory.

        Raises:
            ValueError: If max_size is not a positive integer.
        """
        if not isinstance(max_size, int) or max_size <= 0:
            raise ValueError("max_size must be a positive integer.")

        self.memory = []  # List of dicts: {"color": ..., "message": ..., "is_human": ...}
        self.max_size = max_size
        logger.info(f"ShortTermMemory of {model_name} initialized with max_size={max_size}")

    def add_conversation(self, entry):
        """
        Add a conversation entry to the memory buffer.

        Args:
            entry (dict or str): The conversation entry to add. If str, wraps as {"message": str}.

        Raises:
            TypeError: If entry is not a dict or string.

        Returns:
            None
        """
        if isinstance(entry, str):
            entry = {"message": entry}
        elif not isinstance(entry, dict):
            raise TypeError("entry must be a dict or string.")

        # Ensure memory does not exceed max size
        if len(self.memory) >= self.max_size:
            removed = self.memory.pop(0)
            logger.info("Removed oldest conversation: %s", removed)

        self.memory.append(entry)
        logger.info("Added conversation: %s", entry)

    def add_bulk_conversations(self, entries):
        """
        Add multiple conversation entries at once (e.g., full conversation log).

        Args:
            entries (list): List of dicts (or strings).
        """
        for entry in entries:
            self.add_conversation(entry)

    def get_recent_conversations(self, n=10):
        """
        Get the most recent 'n' conversations from memory.

        Args:
            n (int): Number of recent conversations to retrieve.

        Raises:
            ValueError: If n is not a positive integer.

        Returns:
            list: List of the most recent 'n' conversation dicts.
        """
        if not isinstance(n, int) or n <= 0:
            raise ValueError("n must be a positive integer.")

        logger.info("Retrieving the most recent %d conversations", n)
        return self.memory[-n:]

    def serialize_for_prompt(self):
        """
        Return a string suitable for prompt construction from memory.
        """
        return "\n".join([f"Mr. {e.get('color', '?')}: {e.get('message', '')}" for e in self.memory])

    def clear_memory(self):
        """
        Clear all conversations from the memory buffer.

        Returns:
            None
        """
        self.memory.clear()
        logger.info("Memory cleared.")
