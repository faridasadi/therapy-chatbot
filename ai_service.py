import os
import logging
from openai import OpenAI
from config import OPENAI_API_KEY
from typing import Tuple, List, Dict
from app import get_db_session
from models import Message, UserTheme, User
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI client configuration
MODEL = "gpt-4o-mini"
client = OpenAI(api_key=OPENAI_API_KEY)


def extract_theme_and_sentiment(message: str) -> Tuple[str, float]:
    """Extract the main theme and sentiment from a message using OpenAI."""
    try:
        analysis_prompt = f"""Analyze this message and return a JSON with:
        1. A single main theme/topic (max 3 words)
        2. A sentiment score (-1 to 1)
        Message: {message}"""

        logger.info("Calling OpenAI API for theme and sentiment analysis")
        analysis = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": analysis_prompt
            }],
            max_tokens=100,
            temperature=0.3,
            response_format={"type": "json_object"})

        result = eval(analysis.choices[0].message.content)
        logger.info(f"Theme analysis successful: {result}")
        return result.get('theme', 'general'), result.get('sentiment', 0.0)

    except Exception as e:
        logger.error(f"Theme analysis failed: {str(e)}")
        return 'general', 0.0


def get_user_context(user_id: int, limit: int = 5) -> List[Dict]:
    """Get recent conversation context for the user including themes and sentiments."""
    with get_db_session() as db:
        try:
            recent_messages = (db.query(Message).filter(
                Message.user_id == user_id).order_by(
                    Message.timestamp.desc()).limit(limit).all())

            context = []
            for msg in reversed(recent_messages):
                role = "user" if msg.is_from_user else "assistant"
                message_data = {"role": role, "content": msg.content}
                if msg.theme and msg.sentiment_score is not None:
                    message_data["theme"] = msg.theme
                    message_data["sentiment"] = msg.sentiment_score
                context.append(message_data)
            return context
        except Exception as e:
            logger.error(f"Error getting user context: {str(e)}")
            return []


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
    except Exception as e:
        logger.error(f"Error updating user themes: {str(e)}")
        db.rollback()
    finally:
        db.close()


def get_therapy_response(message: str, user_id: int) -> Tuple[str, str, float]:
    """Get personalized therapy response based on user history and message analysis."""
    with get_db_session() as db:
        try:
            # Extract theme and sentiment
            theme, sentiment = extract_theme_and_sentiment(message)
            logger.info(
                f"Message analysis - Theme: {theme}, Sentiment: {sentiment}")

            # Save user message with theme and sentiment
            from database import save_message
            save_message(user_id, message, True, theme, sentiment)

            # Get user context and preferences
            user = db.query(User).get(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            interaction_style = user.interaction_style
            logger.info(
                f"Retrieved user preferences - Style: {interaction_style}")

            # Build conversation context
            context = get_user_context(user_id)

            # Create personalized system prompt
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

            logger.info("Calling OpenAI API for therapy response")
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7,
                )

                assistant_response = response.choices[0].message.content
                logger.info("Successfully generated therapy response")

                # Save assistant's response with theme
                save_message(user_id, assistant_response, False, theme,
                             sentiment)

                # Update user themes
                update_user_themes(user_id, theme, sentiment)

                return assistant_response, theme, sentiment

            except Exception as api_error:
                logger.error(f"OpenAI API error: {str(api_error)}")
                error_message = "I apologize, but I'm having trouble processing your message right now. Could you try again in a moment?"
                save_message(user_id, error_message, False, "error", 0.0)
                return error_message, "error", 0.0

        except Exception as e:
            logger.error(f"Error in get_therapy_response: {str(e)}")
            error_message = "I apologize, but I'm having trouble processing your message. Could you try rephrasing it?"
            save_message(user_id, error_message, False, "error", 0.0)
            return error_message, "error", 0.0
