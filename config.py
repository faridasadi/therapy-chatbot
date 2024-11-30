import os

# Database configuration
POSTGRES_URI = os.environ.get("DATABASE_URL")

# OpenAI configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Telegram configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PAYMENT_PROVIDER_TOKEN = os.environ.get("TELEGRAM_PAYMENT_TOKEN", "")

# Subscription settings
FREE_MESSAGE_LIMIT = 20
SUBSCRIPTION_PRICE = 15.00
WEEKLY_FREE_MESSAGES = 20
SUBSCRIPTION_DESCRIPTION = "Monthly subscription to Therapyyy Bot - Unlimited access to AI therapy support"
PAYMENT_CURRENCY = "USD"

# Response templates
WELCOME_MESSAGE = """Welcome to Therapyyy! 🌟 
I'm here to provide support and a listening ear. You can start chatting right away - you have 20 free messages to begin with.

Use /help to learn more about how I can assist you."""

SUBSCRIPTION_PROMPT = "To upgrade and have more messages, message to @faridasadi"

HELP_MESSAGE = """Here's how I can help you:
- Chat with me about anything that's on your mind
- Get support and guidance
- Practice mindfulness together

Commands:
/start - Start or restart our conversation
/subscribe - Get unlimited access
/status - Check your remaining messages
/help - Show this help message

Your privacy and security are important to me. All conversations are encrypted and confidential."""
