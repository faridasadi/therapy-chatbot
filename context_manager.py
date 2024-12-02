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
    """Remove expired message contexts periodically and decay relevance scores with optimized batch processing"""
    BATCH_SIZE = 1000  # Process in smaller batches to manage memory
    while True:
        try:
            with get_db_session() as db:
                now = datetime.utcnow()
                week_ago = now - timedelta(days=7)
                
                # Delete expired contexts in batches
                while True:
                    expired = db.query(MessageContext).filter(
                        MessageContext.expires_at <= now
                    ).limit(BATCH_SIZE).all()
                    
                    if not expired:
                        break
                        
                    expired_ids = [c.id for c in expired]
                    db.query(MessageContext).filter(
                        MessageContext.id.in_(expired_ids)
                    ).delete(synchronize_session=False)
                    db.commit()
                    logger.info(f"Cleaned up batch of {len(expired_ids)} expired contexts")
                
                # Decay relevance scores in batches
                processed = 0
                while True:
                    old_contexts = db.query(MessageContext).filter(
                        MessageContext.created_at <= week_ago,
                        MessageContext.relevance_score > 0.2
                    ).limit(BATCH_SIZE).all()
                    
                    if not old_contexts:
                        break
                        
                    for context in old_contexts:
                        age_weeks = (now - context.created_at).days / 7
                        # Apply exponential decay based on age
                        decay_factor = 0.9 ** age_weeks
                        context.relevance_score = max(0.2, context.relevance_score * decay_factor)
                    
                    processed += len(old_contexts)
                    db.commit()
                    logger.info(f"Updated relevance scores for {len(old_contexts)} contexts")
                
                logger.info(f"Context maintenance completed. Processed {processed} old contexts")
                
        except Exception as e:
            logger.error(f"Error in context maintenance: {str(e)}")
            if 'db' in locals():
                db.rollback()
        
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

def get_relevant_context(message_id: int, limit: int = 10, min_relevance: float = 0.2) -> List[Dict]:
    """Get most relevant context for a message with optimized memory usage and longer retention"""
    with get_db_session() as db:
        try:
            # Join with Message table to get theme information
            contexts = db.query(
                MessageContext,
                Message.theme
            ).join(
                Message,
                MessageContext.message_id == Message.id
            ).filter(
                MessageContext.message_id == message_id,
                MessageContext.expires_at > datetime.utcnow(),
                MessageContext.relevance_score >= min_relevance
            ).order_by(
                desc(MessageContext.relevance_score)
            ).limit(limit).all()
            
            return [
                {
                    'type': c.MessageContext.context_key,
                    'value': c.MessageContext.context_value,
                    'relevance': c.MessageContext.relevance_score,
                    'theme': c.theme
                }
                for c in contexts
            ] if contexts else []
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []

# Add context cleanup task to main application
async def start_context_management():
    """Start the context management background tasks"""
    asyncio.create_task(cleanup_expired_contexts())
