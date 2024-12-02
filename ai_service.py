import os
from openai import OpenAI
from config import OPENAI_API_KEY

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
MODEL = "gpt-4o-mini"

client = OpenAI(api_key=OPENAI_API_KEY)

from typing import Tuple, List, Dict
from app import get_db_session
from models import Message, UserTheme, User
from datetime import datetime, timedelta


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


def get_user_context(user_id: int, limit: int = 5):
    """Get recent conversation messages in a simple format for better context management."""
    with get_db_session() as db:
        messages = db.query(Message).filter(
            Message.user_id == user_id
        ).order_by(Message.timestamp.desc()).limit(limit).all()
        return [{"role": "user" if msg.is_from_user else "assistant",
                "content": msg.content} for msg in reversed(messages)]


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


def get_therapy_response(message: str, user_id: int) -> Tuple[str, str, float]:
    """Get personalized therapy response based on user history and message analysis."""
    with get_db_session() as db:
        try:
            # Extract theme and sentiment
            theme, sentiment = extract_theme_and_sentiment(message)

            # Save user message with theme and sentiment
            from database import save_message
            save_message(user_id, message, True, theme, sentiment)

            # Get user context and preferences within the same session
            user = db.query(User).get(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            interaction_style = user.interaction_style

            # Build conversation context with error handling
            try:
                context = get_user_context(user_id)
                if not context:
                    print(f"[Warning] No context retrieved for user {user_id}")
            except Exception as e:
                print(f"[Error] Failed to retrieve context: {str(e)}")
                context = []

            # Verify context formatting
            for ctx in context:
                if not isinstance(ctx, dict) or 'role' not in ctx or 'content' not in ctx:
                    print(f"[Warning] Invalid context format detected: {ctx}")
                    context.remove(ctx)

            # Create focused system prompt with emphasis on memory and context
            system_prompt = f"""You are Therapyyy, an empathetic AI therapy assistant.
            IMPORTANT: You MUST remember and reference information from the conversation history.
            For example:
            - If user mentions their name, use it consistently
            - Reference previous topics they've discussed
            - Maintain continuity of any personal details shared

            Current conversation theme: {theme}
            Your response style should be: {interaction_style}"""

            # Simplified message formatting
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(get_user_context(user_id))
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
