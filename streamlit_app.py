"""
Streamlit app for AI vs I reverse Turing test game with WhatsApp-like UI.

This app provides a chat interface where a human player (Mr. Orange) interacts
with AI participants in a reverse Turing test game.
"""

import random
import re
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from src.AI_vs_I.application.dictionaries import (
    AVAILABLE_GROQ_MODELS,
    COLOR_EMOJIS,
    HUMAN_COLOR,
    PARTICIPANT_COLORS,
)
from src.AI_vs_I.application.game_dynamics import GameDynamics, GamePhase
from src.AI_vs_I.domain.models import Model
from src.AI_vs_I.domain.prompts.prompt_templates import (
    answering_prompt,
    asking_prompt,
    first_asking_prompt,
    guessing_prompt,
)

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI vs I - Reverse Turing Test",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Load external CSS for WhatsApp-like UI
with open("static/style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def initialize_game():
    """Initialize the game state."""
    if "game" not in st.session_state:
        st.session_state.game = GameDynamics(PARTICIPANT_COLORS, HUMAN_COLOR)
        st.session_state.ai_models = {}
        st.session_state.game_started = False
        st.session_state.messages = []
        st.session_state.waiting_for_human_input = False
        st.session_state.human_input_type = None  # "question" or "answer" or "guess"
        st.session_state.current_question = None
        st.session_state.selected_target = None
        st.session_state.guessing_phase_announced = False
        st.session_state.answer_order = []  # Track the order participants answered

        # Initialize model selections with default model for each AI color
        if "model_selections" not in st.session_state:
            st.session_state.model_selections = {
                color: "llama-3.1-8b-instant" for color in PARTICIPANT_COLORS if color != HUMAN_COLOR
            }


def initialize_ai_models():
    """Initialize AI models for non-human participants."""
    if not st.session_state.ai_models:
        with st.spinner("Initializing AI participants..."):
            for color in PARTICIPANT_COLORS:
                if color != HUMAN_COLOR:
                    # Use the selected model for each color
                    model_name = st.session_state.model_selections.get(color, "llama-3.1-8b-instant")
                    st.session_state.ai_models[color] = Model(color=color, model_name=model_name)


def format_conversation_history():
    """Format conversation history for AI models."""
    history = []
    for entry in st.session_state.game.get_conversation_history():
        if entry["type"] == "question":
            history.append(f"Mr. {entry['asker']} asked Mr. {entry['target']}: {entry['question']}")
        elif entry["type"] == "answer":
            history.append(f"Mr. {entry['answerer']} answered: {entry['answer']}")
    return "\n".join(history) if history else "No previous conversation."


def add_chat_message(sender: str, content: str, msg_type: str = "message"):
    """Add a message to the chat display."""
    message = {
        "sender": sender,
        "content": content,
        "type": msg_type,
        "timestamp": datetime.now().strftime("%H:%M"),
    }
    st.session_state.messages.append(message)


def display_chat_messages():
    """Display all chat messages in WhatsApp-like format."""
    chat_container = st.container()
    with chat_container:
        # Start scrollable container
        messages_html = '<div id="chat-container" style="max-height: 40vh; overflow-y: auto; padding-right: 8px;">'

        for msg in st.session_state.messages:
            if msg["type"] == "system":
                messages_html += f'<div class="phase-indicator">{msg["content"]}</div>'
            else:
                is_human = msg["sender"] == HUMAN_COLOR
                message_class = "human-message" if is_human else "ai-message"
                emoji = COLOR_EMOJIS.get(msg["sender"], "💬")

                messages_html += (
                    f'<div class="chat-message {message_class}">'
                    f'<div class="message-header">{emoji} Mr. {msg["sender"]}</div>'
                    f"<div>{msg['content']}</div>"
                    f'<div class="message-time">{msg["timestamp"]}</div>'
                    "</div>"
                )

        # Close scrollable container
        messages_html += "</div>"
        st.markdown(messages_html, unsafe_allow_html=True)


def handle_ai_answer_turn():
    """Handle AI participant answering a question."""
    game = st.session_state.game
    if game.phase != GamePhase.ANSWERING_PHASE:
        return

    # Find the question that was asked to the current participant
    has_pending_question = False
    last_question = None
    for entry in reversed(game.conversation_history):
        if entry["type"] == "question" and entry["target"] == game.current_turn:
            last_question = entry["question"]
            has_pending_question = True
            break

    current_turn = game.current_turn
    participant = game.participants[current_turn]

    # If there's a pending question and this participant hasn't answered yet
    if has_pending_question and not participant.has_answered:
        ai_model = st.session_state.ai_models[current_turn]
        conv_history = format_conversation_history()
        with st.spinner(f"Mr. {current_turn} is answering..."):
            answer = game.invoke_model(
                ai_model.model,
                answering_prompt,
                conversation_history=conv_history,
                question=last_question,
            )
        game.record_answer(current_turn, answer)
        add_chat_message(current_turn, answer, "answer")
        # Track answer order for guessing phase
        if current_turn not in st.session_state.answer_order:
            st.session_state.answer_order.append(current_turn)
        st.rerun()


def handle_ai_asking_turn():
    """Handle AI participant asking a question."""
    game = st.session_state.game
    if game.phase != GamePhase.ASKING_PHASE:
        return

    # Check if it's an AI's turn to ask
    if game.current_turn and game.current_turn != HUMAN_COLOR:
        current_turn = game.current_turn
        participant = game.participants[current_turn]

        # If this participant hasn't asked yet, let them ask
        if not participant.has_asked:
            available_targets = game.get_available_targets(current_turn)
            if available_targets:
                target = random.choice(available_targets)
                ai_model = st.session_state.ai_models[current_turn]
                conv_history = format_conversation_history()
                with st.spinner(f"Mr. {current_turn} is asking..."):
                    if game.question_count == 0:
                        question = game.invoke_model(
                            ai_model.model,
                            first_asking_prompt,
                            target_model=f"Mr. {target}",
                        )
                    else:
                        question = game.invoke_model(
                            ai_model.model,
                            asking_prompt,
                            conversation_history=conv_history,
                            target_model=f"Mr. {target}",
                        )
                game.record_question(current_turn, target, question)
                add_chat_message(current_turn, question, "question")
                st.rerun()


def start_game():
    """Start the game."""
    game = st.session_state.game

    # Reset game if already started
    if st.session_state.game_started:
        game.reset_game()
        st.session_state.messages = []
        st.session_state.guessing_phase_announced = False
        st.session_state.answer_order = []

    # Initialize AI models
    initialize_ai_models()

    # Start the game with a random participant
    starting_participant = random.choice(PARTICIPANT_COLORS)
    game.start_game(starting_participant)

    st.session_state.game_started = True
    add_chat_message(
        "System",
        f"🎮 Game Started! Mr. {starting_participant} will ask the first question.",
        "system",
    )

    # If starting participant is AI, trigger their turn
    if starting_participant != HUMAN_COLOR:
        handle_ai_asking_turn()
    else:
        st.session_state.waiting_for_human_input = True
        st.session_state.human_input_type = "question"


def handle_human_question(target: str, question: str):
    """Handle human asking a question."""
    game = st.session_state.game
    try:
        game.record_question(HUMAN_COLOR, target, question)
        add_chat_message(HUMAN_COLOR, question, "question")
        st.session_state.waiting_for_human_input = False
        st.session_state.selected_target = None
        # Trigger AI response
        st.rerun()
    except ValueError as e:
        st.error(f"Error: {e}")


def handle_human_answer(answer: str):
    """Handle human answering a question."""
    game = st.session_state.game
    try:
        game.record_answer(HUMAN_COLOR, answer)
        add_chat_message(HUMAN_COLOR, answer, "answer")
        st.session_state.waiting_for_human_input = False
        st.session_state.current_question = None
        # Track answer order for guessing phase
        if HUMAN_COLOR not in st.session_state.answer_order:
            st.session_state.answer_order.append(HUMAN_COLOR)
        # Trigger AI response
        st.rerun()
    except ValueError as e:
        st.error(f"Error: {e}")


def handle_human_guess(guess: str, reasoning: str):
    """Handle human making a guess."""
    game = st.session_state.game
    try:
        game.record_guess(HUMAN_COLOR, guess, reasoning)
        add_chat_message(HUMAN_COLOR, f"I think Mr. {guess} is the human. {reasoning}", "guess")
        st.session_state.waiting_for_human_input = False
        st.rerun()
    except ValueError as e:
        st.error(f"Error: {e}")


def main():
    """Main application."""
    st.title("🎭 AI vs I - Reverse Turing Test")

    # Initialize game
    initialize_game()

    # Sidebar
    with st.sidebar:
        st.header("Game Controls")

        if not st.session_state.game_started:
            st.subheader("AI Model Selection")
            st.write("Choose a model for each AI player:")

            # Add model selection dropdown for each AI color
            for color in PARTICIPANT_COLORS:
                if color != HUMAN_COLOR:
                    emoji = COLOR_EMOJIS[color]
                    selected_model = st.selectbox(
                        f"{emoji} Mr. {color}",
                        options=AVAILABLE_GROQ_MODELS,
                        index=AVAILABLE_GROQ_MODELS.index(st.session_state.model_selections[color]),
                        key=f"model_select_{color}",
                    )
                    st.session_state.model_selections[color] = selected_model

            st.divider()

            if st.button("🎮 Start New Game", use_container_width=True):
                start_game()
                st.rerun()
        else:
            if st.button("🔄 Reset Game", use_container_width=True):
                st.session_state.game.reset_game()
                st.session_state.messages = []
                st.session_state.game_started = False
                st.session_state.waiting_for_human_input = False
                st.session_state.guessing_phase_announced = False
                st.session_state.answer_order = []
                st.rerun()

        st.divider()
        st.header("Game Info")
        st.write(f"**You are:** {COLOR_EMOJIS[HUMAN_COLOR]} Mr. {HUMAN_COLOR}")

        if st.session_state.game_started:
            game = st.session_state.game
            st.write(f"**Phase:** {game.phase.value.replace('_', ' ').title()}")
            st.write(f"**Questions Asked:** {game.question_count}/{len(PARTICIPANT_COLORS)}")

            st.divider()
            st.subheader("Participants")
            for color in PARTICIPANT_COLORS:
                participant = game.participants[color]
                emoji = COLOR_EMOJIS[color]
                if color == HUMAN_COLOR:
                    status = "👤 (You)"
                else:
                    model_name = st.session_state.model_selections[color]
                    status = f"🤖 ({model_name})"
                st.write(f"{emoji} Mr. {color} {status}")
                if game.phase == GamePhase.ASKING_PHASE or game.phase == GamePhase.ANSWERING_PHASE:
                    st.write(f"  - Asked: {'✅' if participant.has_asked else '❌'}")
                    st.write(f"  - Answered: {'✅' if participant.has_answered else '❌'}")

    # Main chat area and input controls grouped together
    if not st.session_state.game_started:
        st.info(
            "👋 Welcome to AI vs I! You are Mr. Orange, the human. Try to hide inside the LLM crowd! "
            "You will take turns asking and answering questions with AI participants. "
            "Click 'Start New Game' to begin. If you prefer, select different AI models from the sidebar "
            "before starting."
        )
    else:
        game = st.session_state.game

        if game.current_turn and game.current_turn != HUMAN_COLOR:
            if game.phase == GamePhase.ASKING_PHASE:
                # AI's turn to ask a question
                handle_ai_asking_turn()
                st.rerun()
            elif game.phase == GamePhase.ANSWERING_PHASE:
                # AI's turn to answer a question
                handle_ai_answer_turn()
                st.rerun()

        # Group chat and input controls in one container
        with st.container():
            display_chat_messages()

            # Check if it's human's turn
            is_human_turn = game.current_turn == HUMAN_COLOR
            is_qa_phase = game.phase == GamePhase.ASKING_PHASE or game.phase == GamePhase.ANSWERING_PHASE
            if is_qa_phase and is_human_turn:
                participant = game.participants[HUMAN_COLOR]

                if not participant.has_asked and game.phase == GamePhase.ASKING_PHASE:
                    # Human needs to ask a question
                    st.divider()
                    st.subheader("Your Turn to Ask")

                    available_targets = game.get_available_targets(HUMAN_COLOR)
                    if available_targets:
                        target = st.selectbox(
                            "Select who to ask:",
                            available_targets,
                            format_func=lambda x: f"{COLOR_EMOJIS[x]} Mr. {x}",
                        )

                        question = st.text_input(
                            "Your question:",
                            placeholder=f"Mr. {target}, what do you think about...",
                        )

                        if st.button("Send Question", use_container_width=True):
                            if question.strip():
                                handle_human_question(target, question)
                            else:
                                st.warning("Please enter a question.")

                elif not participant.has_answered and game.phase == GamePhase.ANSWERING_PHASE:
                    # Human needs to answer a question
                    # Find the question asked to human
                    for entry in reversed(game.conversation_history):
                        if entry["type"] == "question" and entry["target"] == HUMAN_COLOR:
                            st.session_state.current_question = entry["question"]
                            break

                    if st.session_state.current_question:
                        st.divider()
                        st.subheader("Your Turn to Answer")
                        st.info(f"Question: {st.session_state.current_question}")

                        answer = st.text_input("Your answer:", placeholder="Type your answer here...")

                        if st.button("Send Answer", use_container_width=True):
                            if answer.strip():
                                handle_human_answer(answer)
                            else:
                                st.warning("Please enter an answer.")

            elif game.phase == GamePhase.GUESSING_PHASE:
                # ============================================================
                # GUESSING PHASE: Everyone guesses who is human
                # ============================================================
                # Participants guess in the same order they answered questions
                # This maintains consistency with the question/answer flow
                # ============================================================

                # Add system message when first entering guessing phase
                if not st.session_state.guessing_phase_announced:
                    add_chat_message(
                        "System",
                        "🎯 Question phase complete! Now it's time to guess who the human is.",
                        "system",
                    )
                    st.session_state.guessing_phase_announced = True

                # Process guesses in answer order
                answer_order = st.session_state.answer_order

                # Find who needs to guess next (in answer order)
                next_to_guess = None
                for color in answer_order:
                    participant = game.participants[color]
                    if participant.guess is None:
                        next_to_guess = color
                        break

                if next_to_guess:
                    if next_to_guess == HUMAN_COLOR:
                        # Human's turn to guess
                        st.divider()
                        st.subheader("Guessing Phase - Your Turn")
                        st.write("Who do you think is the human?")

                        other_participants = [c for c in PARTICIPANT_COLORS if c != HUMAN_COLOR]
                        guess = st.selectbox(
                            "Select your guess:",
                            other_participants,
                            format_func=lambda x: f"{COLOR_EMOJIS[x]} Mr. {x}",
                        )

                        reasoning = st.text_area("Explain your reasoning:", placeholder="I think it's Mr. X because...")

                        if st.button("Submit Guess", use_container_width=True):
                            if reasoning.strip():
                                handle_human_guess(guess, reasoning)
                            else:
                                st.warning("Please provide reasoning for your guess.")
                    else:
                        # AI's turn to guess
                        color = next_to_guess
                        ai_model = st.session_state.ai_models[color]
                        conv_history = format_conversation_history()
                        with st.spinner(f"Mr. {color} is guessing..."):
                            response = game.invoke_model(
                                ai_model.model, guessing_prompt, conversation_history=conv_history, target_model=""
                            )
                        # Extract the color from the response using regex
                        # Expected format: "I think Mr. [Color] is the human because..."
                        guess = color  # Default to self if extraction fails
                        match = re.search(r"I think Mr\.\s+(\w+)\s+is the human", response, re.IGNORECASE)
                        if match:
                            extracted_color = match.group(1)
                            # Validate that the extracted color is a valid participant
                            if extracted_color in PARTICIPANT_COLORS:
                                guess = extracted_color
                        reasoning = response
                        game.record_guess(color, guess, reasoning)
                        add_chat_message(color, f"I think Mr. {guess} is the human. {reasoning}", "guess")
                        st.rerun()
                        return

            elif game.phase == GamePhase.FINISHED:
                # Display results when game is finished
                st.divider()
                st.success("🎉 Game Finished!")

                results = game.get_results()

                # Determine who got the most votes
                vote_counts = {}
                for guess in results["guesses"].values():
                    vote_counts[guess] = vote_counts.get(guess, 0) + 1

                # Find the participant(s) with the most votes
                max_votes = max(vote_counts.values()) if vote_counts else 0
                most_voted = [color for color, count in vote_counts.items() if count == max_votes]

                # Human wins if they are NOT the most voted
                human_won = results["human_color"] not in most_voted

                st.subheader("🏆 Final Verdict")
                if human_won:
                    st.success(f"✅ **HUMAN WINS!** Mr. {results['human_color']} successfully blended in with the AIs!")
                else:
                    human_votes = vote_counts.get(results["human_color"], 0)
                    st.error(
                        f"❌ **HUMAN LOSES!** Mr. {results['human_color']} was identified as the human "
                        f"(received {human_votes} vote(s))"
                    )

                st.divider()
                st.subheader("📊 Vote Summary")
                st.write(f"**The human was:** {COLOR_EMOJIS[results['human_color']]} Mr. {results['human_color']}")

                # Display vote counts for each participant
                for color in PARTICIPANT_COLORS:
                    votes = vote_counts.get(color, 0)
                    emoji = COLOR_EMOJIS[color]
                    is_human = color == results["human_color"]
                    human_tag = " 👤 (HUMAN)" if is_human else ""
                    st.write(f"{emoji} Mr. {color}{human_tag}: **{votes} vote(s)**")

                st.divider()
                st.subheader("🗳️ All Guesses")
                for color, guess in results["guesses"].items():
                    emoji = COLOR_EMOJIS[color]
                    is_correct = guess == results["human_color"]
                    status = "✅" if is_correct else "❌"
                    st.write(f"{status} {emoji} Mr. {color} guessed: {COLOR_EMOJIS[guess]} Mr. {guess}")


if __name__ == "__main__":
    main()
