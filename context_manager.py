from datetime import datetime, timedelta
from sqlalchemy import desc, func
from typing import List, Dict, Optional
from models import MessageContext, Message
from database import get_db_session
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_expired_contexts():
    """Remove expired message contexts periodically"""
    while True:
        try:
            with get_db_session() as db:
                # Delete expired contexts
                expired = db.query(MessageContext).filter(
                    MessageContext.expires_at <= datetime.utcnow()
                ).delete(synchronize_session=False)
                
                db.commit()
                logger.info(f"Cleaned up {expired} expired message contexts")
                
        except Exception as e:
            logger.error(f"Error cleaning up contexts: {str(e)}")
        
        # Run cleanup every hour
        await asyncio.sleep(3600)

def update_context_relevance(message_id: int, context_type: str, value: str) -> None:
    """Update context relevance scores based on usage patterns"""
    with get_db_session() as db:
        try:
            # Get existing context
            context = db.query(MessageContext).filter(
                MessageContext.message_id == message_id,
                MessageContext.context_key == context_type
            ).first()
            
            if not context:
                context = MessageContext(
                    message_id=message_id,
                    context_key=context_type,
                    context_value=value,
                    relevance_score=0.5,  # Initial middle score
                    expires_at=datetime.utcnow() + timedelta(days=30)  # Default 30 day expiry
                )
                db.add(context)
            
            # Update relevance based on message sentiment and theme consistency
            message = db.query(Message).get(message_id)
            if message:
                # Find similar contexts
                similar_contexts = db.query(MessageContext).join(Message).filter(
                    Message.theme == message.theme,
                    MessageContext.context_key == context_type,
                    MessageContext.context_value == value
                ).order_by(desc(MessageContext.relevance_score)).limit(5).all()
                
                # Adjust relevance based on similar contexts
                if similar_contexts:
                    avg_relevance = sum(c.relevance_score for c in similar_contexts) / len(similar_contexts)
                    context.relevance_score = (context.relevance_score + avg_relevance) / 2
                
            db.commit()
            
        except Exception as e:
            logger.error(f"Error updating context relevance: {str(e)}")
            db.rollback()

def get_relevant_context(message_id: int, limit: int = 5) -> List[Dict]:
    """Get most relevant context for a message"""
    with get_db_session() as db:
        contexts = db.query(MessageContext).filter(
            MessageContext.message_id == message_id,
            MessageContext.expires_at > datetime.utcnow()
        ).order_by(
            desc(MessageContext.relevance_score)
        ).limit(limit).all()
        
        return [
            {
                'type': c.context_key,
                'value': c.context_value,
                'relevance': c.relevance_score
            }
            for c in contexts
        ]

# Add context cleanup task to main application
async def start_context_management():
    """Start the context management background tasks"""
    asyncio.create_task(cleanup_expired_contexts())
