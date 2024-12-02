import os
from openai import OpenAI
from config import OPENAI_API_KEY

# Updated as requested by manager
MODEL = "gpt-4"

client = OpenAI(api_key=OPENAI_API_KEY)

from typing import Tuple, List, Dict
from database import get_db_session, save_message
from models import Message, UserTheme, User
from datetime import datetime, timedelta
import logging
import time
from monitoring import pipeline_monitor, monitor_pipeline_stage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_theme_and_sentiment(message: str) -> Tuple[str, float]:
    """Extract the main theme and sentiment from a message using OpenAI."""
    try:
        analysis_prompt = f"""Analyze this message and return a JSON with:
        1. A single main theme/topic (max 3 words)
        2. A sentiment score (-1 to 1)
        Message: {message}"""

        analysis = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": analysis_prompt
            }],
            max_tokens=100,
            temperature=0.3,
        )

        result = eval(analysis.choices[0].message.content)
        return result.get('theme', 'general'), result.get('sentiment', 0.0)
    except:
        return 'general', 0.0


def get_user_context(user_id: int,
                     limit: int = 5,
                     time_window: int = 24) -> List[Dict]:
    """Get recent conversation context for the user including themes, sentiments, and relevant context."""
    with get_db_session() as db:
        try:
            # Get recent messages within time window
            cutoff_time = datetime.utcnow() - timedelta(hours=time_window)
            recent_messages = (db.query(Message).filter(
                Message.user_id == user_id, Message.timestamp
                >= cutoff_time).order_by(
                    Message.timestamp.desc()).limit(limit).all())

            context = []
            theme_continuity = {}  # Track theme continuity

            for msg in reversed(recent_messages):
                role = "user" if msg.is_from_user else "assistant"
                message_data = {
                    "role": role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }

                # Include theme and sentiment with continuity tracking
                if msg.theme:
                    message_data["theme"] = msg.theme
                    theme_continuity[msg.theme] = theme_continuity.get(
                        msg.theme, 0) + 1

                if msg.sentiment_score is not None:
                    message_data["sentiment"] = msg.sentiment_score

                # Get additional context from MessageContext
                message_contexts = get_relevant_context(msg.id,
                                                        limit=3,
                                                        min_relevance=0.4)
                if message_contexts:
                    message_data["additional_context"] = message_contexts

                context.append(message_data)

            # Add theme continuity information
            if context:
                dominant_theme = max(
                    theme_continuity.items(),
                    key=lambda x: x[1])[0] if theme_continuity else None
                context[0]["dominant_theme"] = dominant_theme

            return context
        except Exception as e:
            logger.error(f"Error getting user context: {str(e)}")
            return []  # Return empty context on error


def update_user_themes(user_id: int, theme: str, sentiment: float):
    """Update or create user theme statistics."""
    db = get_db_session()
    try:
        user_theme = (db.query(UserTheme).filter(
            UserTheme.user_id == user_id, UserTheme.theme == theme).first())

        if user_theme:
            user_theme.frequency += 1
            user_theme.sentiment = (user_theme.sentiment + sentiment) / 2
            user_theme.last_mentioned = datetime.utcnow()
        else:
            user_theme = UserTheme(user_id=user_id,
                                   theme=theme,
                                   sentiment=sentiment)
            db.add(user_theme)

        db.commit()
    finally:
        db.close()


@monitor_pipeline_stage("ai_response_generation")
def get_therapy_response(message: str, user_id: int) -> Tuple[str, str, float]:
    """Get personalized therapy response based on user history and message analysis."""
    with get_db_session() as db:
        try:
            # Extract theme and sentiment
            start_time = time.time()
            theme, sentiment = extract_theme_and_sentiment(message)
            pipeline_monitor.record_api_call(time.time() - start_time)

            # Save user message with theme and sentiment
            from database import save_message
            save_message(user_id, message, True, theme, sentiment)

            # Get user context and preferences within the same session
            user = db.query(User).get(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            interaction_style = user.interaction_style

            # Build conversation context
            context = get_user_context(user_id)

            # Create personalized system prompt with theme awareness
            system_prompt = f"""You are Therapyyy, an empathetic and supportive AI therapy assistant.
            Current conversation theme: {theme}
            User's preferred interaction style: {interaction_style}
            
            Your responses should be:
            - Compassionate and understanding
            - Non-judgmental
            - Professional but warm
            - Focused on emotional support
            - Clear and concise
            - Aligned with the user's interaction style: {interaction_style}
            
            Never provide medical advice or diagnoses. If someone needs immediate help,
            direct them to professional emergency services."""

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
            ]
            messages.extend(context)
            messages.append({"role": "user", "content": message})

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )

            # Get assistant's response
            assistant_response = response.choices[0].message.content

            # Save assistant's response with theme
            save_message(user_id, assistant_response, False, theme, sentiment)

            # Update user themes
            update_user_themes(user_id, theme, sentiment)

            return assistant_response, theme, sentiment

        except Exception as e:
            print(f"Error in get_therapy_response: {str(e)}")
            # Save error message to maintain conversation continuity
            error_message = "I apologize, but I'm having trouble processing your message. Could you try rephrasing it?"
            save_message(user_id, error_message, False, "error", 0.0)
            return error_message, "error", 0.0
