import os
from openai import OpenAI
from config import OPENAI_API_KEY

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
MODEL = "gpt-4o"

client = OpenAI(api_key=OPENAI_API_KEY)

def get_therapy_response(message: str, context: list = None) -> str:
    try:
        system_prompt = """You are Therapyyy, an empathetic and supportive AI therapy assistant. 
        Your responses should be:
        - Compassionate and understanding
        - Non-judgmental
        - Professional but warm
        - Focused on emotional support
        - Clear and concise
        
        Never provide medical advice or diagnoses. If someone needs immediate help,
        direct them to professional emergency services."""
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        if context:
            messages.extend(context)
            
        messages.append({"role": "user", "content": message})
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return "I apologize, but I'm having trouble processing your message. Could you try rephrasing it?"
