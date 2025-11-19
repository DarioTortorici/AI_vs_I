from enum import Enum

from langchain_core.prompts import ChatPromptTemplate

from AI_vs_I.infrastructure.monitoring.logger import Logger


class GamePhase(Enum):
    """Game phase enumeration."""

    NOT_STARTED = "not_started"
    ASKING_PHASE = "asking_phase"
    ANSWERING_PHASE = "answering_phase"
    GUESSING_PHASE = "guessing_phase"
    FINISHED = "finished"

    def __str__(self):
        return self.value


class ParticipantState:
    """Tracks the state of a single participant."""

    def __init__(self, color: str, is_human: bool = False):
        """
        Initialize participant state.

        Args:
            color (str): The color identifier for the participant (e.g., "Red", "Blue").
            is_human (bool): Whether this participant is human. Defaults to False.
        """
        self.color = color
        self.is_human = is_human
        self.has_asked = False
        self.has_answered = False
        self.guess: str | None = None

    def reset(self):
        """Reset participant state for a new game."""
        self.has_asked = False
        self.has_answered = False
        self.guess = None

    def __str__(self):
        return f"ParticipantState(color={self.color}, is_human={self.is_human}, has_asked={self.has_asked}, has_answered={self.has_answered}, guess={self.guess})"


class GameDynamics:
    """
    Manages game flow, enforcing rules, and tracking turns for the AI vs I reverse Turing test.

    Responsibilities:
    - Track participants and their states (has_asked, has_answered)
    - Enforce game rules (each participant asks and answers once)
    - Manage game phases (question phase, guessing phase)
    - Track current turn
    - Validate moves
    - Determine game completion
    """

    def __init__(self, participant_colors: list[str], human_color: str = "Orange"):
        """
        Initialize the game dynamics.

        Args:
            participant_colors (list[str]): List of color identifiers for all participants.
            human_color (str): The color identifier for the human participant. Defaults to "Orange".

        Raises:
            ValueError: If participant_colors is empty or human_color is not in participant_colors.
        """
        if not participant_colors:
            raise ValueError("participant_colors cannot be empty")
        if human_color not in participant_colors:
            raise ValueError(f"human_color '{human_color}' must be in participant_colors")

        self.logger = Logger.get_logger(__name__)
        self.participants: dict[str, ParticipantState] = {}
        self.human_color = human_color
        self.current_turn: str | None = None
        self.phase = GamePhase.NOT_STARTED
        self.question_count = 0
        self.conversation_history: list[dict] = []

        # Initialize participants
        for color in participant_colors:
            self.participants[color] = ParticipantState(color, is_human=(color == human_color))

        self.logger.info(f"Game initialized with {len(self.participants)} participants. Human: Mr. {human_color}")

    def start_game(self, starting_participant: str):
        """
        Start the game with a specific participant.

        Args:
            starting_participant (str): The color of the participant who starts the game.

        Raises:
            ValueError: If the game has already started or starting_participant is invalid.
        """
        if self.phase != GamePhase.NOT_STARTED:
            raise ValueError(f"Game has already started (current phase: {self.phase.value})")
        if starting_participant not in self.participants:
            raise ValueError(f"Invalid starting participant: {starting_participant}")

        self.phase = GamePhase.ASKING_PHASE
        self.current_turn = starting_participant
        self.logger.info(f"Game started! Mr. {starting_participant} goes first.")

    def record_question(self, asker: str, target: str, question: str):
        """
        Record a question from one participant to another.

        Args:
            asker (str): The color of the participant asking the question.
            target (str): The color of the participant being asked.
            question (str): The question being asked.

        Raises:
            ValueError: If the move is invalid (wrong phase, wrong turn, already asked, etc.).
        """
        # Validate game state
        if self.phase != GamePhase.ASKING_PHASE:
            raise ValueError(f"Cannot ask questions in phase: {self.phase.value}")

        # Validate asker
        if asker not in self.participants:
            raise ValueError(f"Invalid asker: {asker}")
        if self.current_turn is not None and asker != self.current_turn:
            raise ValueError(f"It's not Mr. {asker}'s turn (current turn: Mr. {self.current_turn})")
        if self.participants[asker].has_asked:
            raise ValueError(f"Mr. {asker} has already asked a question")

        # Validate target
        if target not in self.participants:
            raise ValueError(f"Invalid target: {target}")
        if asker == target:
            raise ValueError("Cannot ask a question to yourself")

        # Record the question
        self.participants[asker].has_asked = True
        self.question_count += 1
        self.current_turn = target

        # Add to conversation history
        entry = {"asker": asker, "target": target, "question": question, "type": "question"}
        self.conversation_history.append(entry)

        self.logger.info(f"Mr. {asker} asked Mr. {target}: {question}")
        self.phase = GamePhase.ANSWERING_PHASE

    def record_answer(self, answerer: str, answer: str):
        """
        Record an answer from a participant.

        Args:
            answerer (str): The color of the participant answering.
            answer (str): The answer being provided.

        Raises:
            ValueError: If the move is invalid (wrong phase, wrong turn, already answered, etc.).
        """
        # Validate game state
        if self.phase != GamePhase.ANSWERING_PHASE:
            raise ValueError(f"Cannot answer questions in phase: {self.phase.value}")

        # Validate answerer
        if answerer not in self.participants:
            raise ValueError(f"Invalid answerer: {answerer}")
        if self.current_turn != answerer:
            raise ValueError(f"It's not Mr. {answerer}'s turn to answer (current turn: Mr. {self.current_turn})")
        if self.participants[answerer].has_answered:
            raise ValueError(f"Mr. {answerer} has already answered a question")

        # Record the answer
        self.participants[answerer].has_answered = True

        # Add to conversation history
        entry = {"answerer": answerer, "answer": answer, "type": "answer"}
        self.conversation_history.append(entry)

        self.logger.info(f"Mr. {answerer} answered: {answer}")

        # Update current_turn for next action
        # If answerer hasn't asked yet, they should ask next (keep current_turn)
        # Otherwise, find next person who needs to answer
        if not self.participants[answerer].has_asked:
            # Answerer will ask next, keep current_turn as is
            pass
        else:
            # Find next person who has been asked a question but hasn't answered yet
            self.current_turn = self._find_next_answerer()

        # Check if question phase is complete
        if self._is_q_and_a_phase_complete():
            self._transition_to_guessing_phase()
        else:
            self.phase = GamePhase.ASKING_PHASE

    def record_guess(self, guesser: str, guess: str, reasoning: str = ""):
        """
        Record a participant\'s guess about who the human is.

        Args:
            guesser (str): The color of the participant making the guess.
            guess (str): The color of the participant they believe is human.
            reasoning (str): The reasoning for their guess. Defaults to "".

        Raises:
            ValueError: If the move is invalid (wrong phase, invalid guess, etc.).
        """
        # Validate game state
        if self.phase != GamePhase.GUESSING_PHASE:
            raise ValueError(f"Cannot make guesses in phase: {self.phase.value}")

        # Validate guesser
        if guesser not in self.participants:
            raise ValueError(f"Invalid guesser: {guesser}")
        if self.participants[guesser].guess is not None:
            raise ValueError(f"Mr. {guesser} has already made a guess")

        # Validate guess
        if guess not in self.participants:
            raise ValueError(f"Invalid guess target: {guess}")

        # Record the guess
        self.participants[guesser].guess = guess

        # Add to conversation history
        entry = {"guesser": guesser, "guess": guess, "reasoning": reasoning, "type": "guess"}
        self.conversation_history.append(entry)

        self.logger.info(f"Mr. {guesser} guessed Mr. {guess} is the human. Reasoning: {reasoning}")

        # Check if all guesses are complete
        if self._are_all_guesses_complete():
            self.phase = GamePhase.FINISHED
            

    def get_available_targets(self, curr_asker: str) -> list[str]:
        """
        Get list of valid targets for a partici""pant to ask.
        "Return valid targets for a participant to ask, following game rules.

        Args:
            curr_asker (str): The color of the participant who is asking the question.
        Returns:
            list[str]: List of valid target participant colors.
        """
        # Exclude self
        possible_targets = [c for c in self.participants if c != curr_asker]

        # Exclude those who have already been asked a question
        # (each participant should be asked exactly once)
        asked_targets = set()
        for entry in self.conversation_history:
            if entry["type"] == "question":
                asked_targets.add(entry["target"])
        possible_targets = [c for c in possible_targets if c not in asked_targets]

        # For the first question, anyone can be asked
        if self.question_count == 0:
            return possible_targets

        # Determine if curr_asker is the last to ask (i.e., all others have asked)
        others = [c for c in self.participants if c != curr_asker]
        others_asked = [self.participants[c].has_asked for c in others]
        is_last_asker = all(others_asked)

        if not is_last_asker:
            # Exclude those who have already asked (they've had their turn to ask)
            # Only ask those who haven't asked yet (they're next in the question sequence)
            possible_targets = [c for c in possible_targets if not self.participants[c].has_asked]

        return possible_targets

    def get_game_state(self) -> dict:
        """
        Get the current state of the game.

        Returns:
            dict: Dictionary containing game state information.
        """
        return {
            "phase": self.phase.value,
            "current_turn": self.current_turn,
            "question_count": self.question_count,
            "participants": {
                color: {
                    "has_asked": state.has_asked,
                    "has_answered": state.has_answered,
                    "guess": state.guess,
                    "is_human": state.is_human,
                }
                for color, state in self.participants.items()
            },
            "conversation_history": self.conversation_history,
        }

    def get_conversation_history(self) -> list[dict]:
        """
        Get the conversation history.

        Returns:
            list[dict]: List of conversation entries.
        """
        return self.conversation_history.copy()

    def is_game_finished(self) -> bool:
        """
        Check if the game is finished.

        Returns:
            bool: True if the game is finished, False otherwise.
        """
        return self.phase == GamePhase.FINISHED

    def get_results(self) -> dict:
        """
        Get the game results after the game is finished.

        Returns:
            dict: Dictionary containing game results including guesses and the actual human.

        Raises:
            ValueError: If the game is not finished yet.
        """
        if not self.is_game_finished():
            raise ValueError("Game is not finished yet")

        guesses = {color: state.guess for color, state in self.participants.items() if state.guess is not None}

        # Count correct guesses
        correct_guesses = sum(1 for guess in guesses.values() if guess == self.human_color)

        return {
            "human_color": self.human_color,
            "guesses": guesses,
            "correct_guesses": correct_guesses,
            "total_participants": len(self.participants),
        }

    def reset_game(self):
        """Reset the game to initial state."""
        for participant in self.participants.values():
            participant.reset()

        self.current_turn = None
        self.phase = GamePhase.NOT_STARTED
        self.question_count = 0
        self.conversation_history.clear()

        self.logger.info("Game reset to initial state")

    def _find_next_answerer(self) -> str | None:
        """
        Find the next participant who has been asked a question but hasn't answered yet.

        Returns:
            Optional[str]: The color of the next participant who needs to answer, or None if everyone has answered.
        """
        # Look through conversation history to find unanswered questions
        for entry in self.conversation_history:
            if entry["type"] == "question":
                target = entry["target"]
                if not self.participants[target].has_answered:
                    return target
        return None

    def _is_q_and_a_phase_complete(self) -> bool:
        """
        Check if all participants have asked and answered questions.

        Returns:
            bool: True if question phase is complete, False otherwise.
        """
        return all(state.has_asked and state.has_answered for state in self.participants.values())

    def _are_all_guesses_complete(self) -> bool:
        """
        Check if all participants have made their guesses.

        Returns:
            bool: True if all guesses are complete, False otherwise.
        """
        return all(state.guess is not None for state in self.participants.values())

    def _transition_to_guessing_phase(self):
        """Transition the game to the guessing phase."""
        self.phase = GamePhase.GUESSING_PHASE
        self.current_turn = None
        self.logger.info("Game transitioned to guessing phase")

    def _finish_game(self):
        """Mark the game as finished."""
        self.phase = GamePhase.FINISHED
        self.logger.info("Game finished!")

    def invoke_model(self, agent, chat_prompt: ChatPromptTemplate, **prompt_vars) -> str:
        """
        Invoke a model agent with a formatted prompt and extract the response.

        This method follows the standard pattern for invoking LangChain agents:
        1. Format the prompt with provided variables
        2. Invoke the agent with the formatted prompt
        3. Extract the final message content from the response

        Args:
            agent: The LangChain agent to invoke (from Model.model)
            chat_prompt: The ChatPromptTemplate to format
            **prompt_vars: Variables to format the prompt with

        Returns:
            str: The extracted response message content

        Raises:
            Exception: If invocation fails
        """
        try:
            # Format the prompt with the provided variables
            formatted_prompt = chat_prompt.format(**prompt_vars)

            # Invoke the agent with the formatted prompt
            response = agent.invoke({"messages": [{"role": "user", "content": formatted_prompt}]})

            # Always extract the final message for frontend display
            last_msg = None
            if isinstance(response, dict) and "messages" in response:
                messages = response["messages"]
                if messages:
                    last_msg_obj = messages[-1]
                    # If it's a dict or an object with a 'content' attribute
                    if isinstance(last_msg_obj, dict):
                        last_msg = last_msg_obj.get("content", str(last_msg_obj))
                    else:
                        last_msg = getattr(last_msg_obj, "content", str(last_msg_obj))
                if last_msg is None:
                    last_msg = str(response)
                return last_msg.strip()
            # If response is a string, just return it
            if isinstance(response, str):
                return response.strip()
            return str(response)
        except Exception as e:
            self.logger.error(f"Error invoking model: {e}")
            raise

    def __str__(self):
        return f"GameDynamics(phase={self.phase}, current_turn={self.current_turn}, participants={self.participants})"
