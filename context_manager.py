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
    """Remove expired message contexts periodically and decay relevance scores"""
    while True:
        try:
            with get_db_session() as db:
                # Delete expired contexts
                expired = db.query(MessageContext).filter(
                    MessageContext.expires_at <= datetime.utcnow()
                ).delete(synchronize_session=False)
                
                # Decay relevance scores for old contexts
                old_contexts = db.query(MessageContext).filter(
                    MessageContext.created_at <= datetime.utcnow() - timedelta(days=7),
                    MessageContext.relevance_score > 0.2
                ).all()
                
                for context in old_contexts:
                    # Decay by 10% every week
                    context.relevance_score = max(0.2, context.relevance_score * 0.9)
                
                db.commit()
                logger.info(f"Cleaned up {expired} expired contexts and updated {len(old_contexts)} old contexts")
                
        except Exception as e:
            logger.error(f"Error in context maintenance: {str(e)}")
        
        # Run maintenance every hour
        await asyncio.sleep(3600)

def update_context_relevance(message_id: int, context_type: str, value: str, batch_size: int = 100) -> None:
    """Update context relevance scores based on usage patterns with batch processing"""
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
                # Find similar contexts efficiently using indices
                similar_contexts = db.query(MessageContext).join(Message).filter(
                    Message.theme == message.theme,
                    MessageContext.context_key == context_type,
                    MessageContext.context_value == value,
                    MessageContext.relevance_score > 0.3  # Filter low relevance contexts
                ).order_by(
                    desc(MessageContext.relevance_score)
                ).limit(batch_size).all()
                
                if similar_contexts:
                    # Calculate weighted average based on recency
                    total_weight = 0
                    weighted_sum = 0
                    now = datetime.utcnow()
                    
                    for c in similar_contexts:
                        age = (now - c.created_at).days + 1
                        weight = 1.0 / age  # More recent contexts have higher weight
                        weighted_sum += c.relevance_score * weight
                        total_weight += weight
                    
                    if total_weight > 0:
                        weighted_avg = weighted_sum / total_weight
                        # Smooth update with momentum
                        context.relevance_score = (0.7 * context.relevance_score) + (0.3 * weighted_avg)
                
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
