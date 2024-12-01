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


def get_user_context(user_id: int, limit: int = 5) -> Tuple[List[Dict], Dict]:
    """Get recent conversation context and user profile information."""
    with get_db_session() as db:
        try:
            # Get user profile information in an atomic transaction
            user = db.query(User).get(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            # Create user profile context
            profile_context = {
                "name": user.first_name,
                "interaction_style": user.interaction_style,
                "age": user.age,
                "gender": user.gender,
                "therapy_experience": user.therapy_experience,
                "primary_concerns": user.primary_concerns,
                "background_completed": user.background_completed
            }

            # Get recent messages with themes and sentiments
            recent_messages = (db.query(Message)
                             .filter(Message.user_id == user_id)
                             .order_by(Message.timestamp.desc())
                             .limit(limit)
                             .all())

            message_context = []
            for msg in reversed(recent_messages):
                role = "user" if msg.is_from_user else "assistant"
                message_data = {
                    "role": role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                }
                if msg.theme and msg.sentiment_score is not None:
                    message_data.update({
                        "theme": msg.theme,
                        "sentiment": msg.sentiment_score
                    })
                message_context.append(message_data)

            return message_context, profile_context

        except Exception as e:
            print(f"Error getting user context: {str(e)}")
            return [], {}  # Return empty contexts on error for graceful degradation

def update_user_profile_from_conversation(user_id: int, message: str) -> bool:
    """Update user profile information based on conversation content."""
    try:
        profile_analysis_prompt = f"""Analyze this message for any personal information shared by the user. 
        Return a JSON with any of these fields if mentioned (leave others empty):
        - name: user's first name if mentioned
        - age: numerical age if mentioned
        - gender: gender identity if mentioned
        - therapy_experience: any mentioned therapy experience
        - primary_concerns: main issues or concerns mentioned
        
        Message: {message}"""

        analysis = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": profile_analysis_prompt}],
            max_tokens=150,
            temperature=0.3,
        )

        profile_data = eval(analysis.choices[0].message.content)
        
        if not profile_data:
            return False

        with get_db_session() as db:
            user = db.query(User).get(user_id)
            if not user:
                return False

            # Update only fields that are present in the analysis
            if 'name' in profile_data and profile_data['name']:
                user.first_name = profile_data['name']
            if 'age' in profile_data and profile_data['age']:
                try:
                    user.age = int(profile_data['age'])
                except (ValueError, TypeError):
                    pass
            if 'gender' in profile_data and profile_data['gender']:
                user.gender = profile_data['gender']
            if 'therapy_experience' in profile_data and profile_data['therapy_experience']:
                user.therapy_experience = profile_data['therapy_experience']
            if 'primary_concerns' in profile_data and profile_data['primary_concerns']:
                user.primary_concerns = profile_data['primary_concerns']

            db.commit()
            return True

    except Exception as e:
        print(f"Error updating user profile from conversation: {str(e)}")
        return False



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
    """Get personalized therapy response based on user history, profile, and message analysis."""
    with get_db_session() as db:
        try:
            # Extract theme and sentiment
            theme, sentiment = extract_theme_and_sentiment(message)

            # Update user profile from conversation
            update_user_profile_from_conversation(user_id, message)

            # Save user message with theme and sentiment
            from database import save_message
            save_message(user_id, message, True, theme, sentiment)

            # Get user context and profile information
            message_context, profile_context = get_user_context(user_id)

            # Create personalized system prompt with user profile information
            name_greeting = f"Hello {profile_context['name']}" if profile_context.get('name') else "Hello"
            background_info = ""
            
            if profile_context.get('age'):
                background_info += f"\nUser age: {profile_context['age']}"
            if profile_context.get('gender'):
                background_info += f"\nUser gender identity: {profile_context['gender']}"
            if profile_context.get('therapy_experience'):
                background_info += f"\nTherapy experience: {profile_context['therapy_experience']}"
            if profile_context.get('primary_concerns'):
                background_info += f"\nPrimary concerns: {profile_context['primary_concerns']}"

            system_prompt = f"""You are Therapyyy, an empathetic and supportive AI therapy assistant.
            {name_greeting}
            
            User Background Information:{background_info}
            Current conversation theme: {theme}
            User's preferred interaction style: {profile_context.get('interaction_style', 'balanced')}
            
            Your responses should be:
            - Compassionate and understanding
            - Non-judgmental
            - Professional but warm
            - Focused on emotional support
            - Clear and concise
            - Personalized based on the user's background
            - Aligned with the user's interaction style
            
            Never provide medical advice or diagnoses. If someone needs immediate help,
            direct them to professional emergency services."""

            # Prepare conversation messages
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add message context
            for msg in message_context:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            messages.append({"role": "user", "content": message})

            # Get AI response
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )

            # Get assistant's response
            assistant_response = response.choices[0].message.content

            # Save assistant's response with theme and update context
            save_message(user_id, assistant_response, False, theme, sentiment)
            update_user_themes(user_id, theme, sentiment)

            return assistant_response, theme, sentiment

        except Exception as e:
            print(f"Error in get_therapy_response: {str(e)}")
            error_message = "I apologize, but I'm having trouble processing your message. Could you try rephrasing it?"
            save_message(user_id, error_message, False, "error", 0.0)
            return error_message, "error", 0.0
