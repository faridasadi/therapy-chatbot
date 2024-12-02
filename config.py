import os
from typing import Final

# OpenAI configuration
OPENAI_API_KEY: Final = os.environ.get("OPENAI_API_KEY")

# Telegram configuration
TELEGRAM_TOKEN: Final = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN or not TELEGRAM_TOKEN.strip():
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set or empty")

# Webhook configuration
WEBHOOK_URL: Final = os.environ.get("WEBHOOK_URL")
WEBHOOK_PORT: Final = int(os.environ.get("WEBHOOK_PORT", "8443"))
USE_WEBHOOK: Final = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
# Database configuration
DATABASE_URL: Final = os.environ.get("DATABASE_URL")

# Message limits and quotas
FREE_MESSAGE_LIMIT: Final = 200
WEEKLY_FREE_MESSAGES: Final = 200

# Bot response templates
WELCOME_MESSAGE: Final = """👋🏻 Hey. What's on your mind today?"""

SUBSCRIPTION_PROMPT: Final = "To upgrade and have more messages, message to @faridasadi"

HELP_MESSAGE: Final = """Here's how I can help you:
- Chat with me about anything that's on your mind
- Get support and guidance
- Practice mindfulness together

Commands:
/start - Start or restart our conversation
/subscribe - Get unlimited access
/status - Check your remaining messages
/help - Show this help message

Your privacy and security are important to me. All conversations are encrypted and confidential."""
