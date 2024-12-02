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
    """Update context relevance scores with improved continuity and semantic relevance"""
    with get_db_session() as db:
        try:
            # Get existing context
            context = db.query(MessageContext).filter(
                MessageContext.message_id == message_id,
                MessageContext.context_key == context_type
            ).first()
            
            if not context:
                # Initialize with dynamic expiry based on context type
                expiry_days = {
                    'theme': 60,
                    'emotion': 45,
                    'topic': 30,
                    'reference': 15
                }.get(context_type.lower(), 30)
                
                context = MessageContext(
                    message_id=message_id,
                    context_key=context_type,
                    context_value=value,
                    relevance_score=0.6,  # Start with slightly higher initial score
                    expires_at=datetime.utcnow() + timedelta(days=expiry_days)
                )
                db.add(context)
            
            # Get message and its metadata
            message = db.query(Message).get(message_id)
            if message:
                # Enhanced context similarity search
                similar_contexts = db.query(MessageContext, Message).join(Message).filter(
                    Message.theme == message.theme,
                    MessageContext.context_key == context_type,
                    MessageContext.context_value == value,
                    MessageContext.relevance_score > 0.4,  # Increased minimum relevance threshold
                    Message.timestamp >= datetime.utcnow() - timedelta(days=30)  # Recent messages only
                ).order_by(
                    desc(MessageContext.relevance_score),
                    desc(Message.timestamp)
                ).limit(batch_size).all()
                
                if similar_contexts:
                    # Enhanced weighted scoring system
                    total_weight = 0
                    weighted_sum = 0
                    now = datetime.utcnow()
                    
                    for context_msg_pair in similar_contexts:
                        c, msg = context_msg_pair
                        # Calculate multi-factor weight
                        age_weight = 1.0 / ((now - c.created_at).days + 1)  # Time decay
                        
                        # Theme consistency bonus
                        theme_bonus = 1.2 if msg.theme == message.theme else 1.0
                        
                        # Sentiment alignment bonus
                        sentiment_bonus = 1.0
                        if msg.sentiment_score is not None and message.sentiment_score is not None:
                            sentiment_diff = abs(msg.sentiment_score - message.sentiment_score)
                            sentiment_bonus = 1.2 if sentiment_diff < 0.3 else 1.0
                        
                        # Combined weight
                        weight = age_weight * theme_bonus * sentiment_bonus
                        
                        weighted_sum += c.relevance_score * weight
                        total_weight += weight
                    
                    if total_weight > 0:
                        weighted_avg = weighted_sum / total_weight
                        # Adaptive momentum based on context age
                        age_factor = min(1.0, (now - context.created_at).days / 30)
                        momentum = 0.8 - (0.3 * age_factor)  # Reduce momentum for older contexts
                        context.relevance_score = (momentum * context.relevance_score) + ((1 - momentum) * weighted_avg)
                        
                        # Boost score for highly consistent contexts
                        if len(similar_contexts) >= 3 and weighted_avg > 0.8:
                            context.relevance_score = min(1.0, context.relevance_score * 1.1)
                
                # Update expiry based on relevance
                if context.relevance_score > 0.8:
                    context.expires_at = max(context.expires_at, datetime.utcnow() + timedelta(days=60))
                
            db.commit()
            
        except Exception as e:
            logger.error(f"Error updating context relevance: {str(e)}")
            db.rollback()

def get_relevant_context(message_id: int, limit: int = 5, min_relevance: float = 0.3) -> List[Dict]:
    """Get most relevant context for a message with enhanced history retrieval and error handling"""
    with get_db_session() as db:
        try:
            # Get the message to find its timestamp and user_id
            message = db.query(Message).get(message_id)
            if not message:
                logger.error(f"Message {message_id} not found")
                return []

            # Get recent conversation history
            recent_messages = db.query(Message).filter(
                Message.user_id == message.user_id,
                Message.timestamp <= message.timestamp,
                Message.id != message_id
            ).order_by(
                desc(Message.timestamp)
            ).limit(5).all()

            # Get contexts for the current message and recent messages
            message_ids = [m.id for m in recent_messages] + [message_id]
            
            contexts = db.query(
                MessageContext,
                Message.theme,
                Message.timestamp,
                Message.sentiment_score
            ).join(
                Message,
                MessageContext.message_id == Message.id
            ).filter(
                MessageContext.message_id.in_(message_ids),
                MessageContext.expires_at > datetime.utcnow(),
                MessageContext.relevance_score >= min_relevance
            ).order_by(
                desc(Message.timestamp),
                desc(MessageContext.relevance_score)
            ).limit(limit * 2).all()  # Get more contexts initially for better filtering

            # Enhanced context processing with relevance boosting
            processed_contexts = []
            for c in contexts:
                context_data = {
                    'type': c.MessageContext.context_key,
                    'value': c.MessageContext.context_value,
                    'relevance': c.MessageContext.relevance_score,
                    'theme': c.theme,
                    'timestamp': c.timestamp.isoformat()
                }

                # Boost relevance for thematic consistency
                if message.theme == c.theme:
                    context_data['relevance'] *= 1.2

                # Boost relevance for emotional consistency
                if message.sentiment_score is not None and c.sentiment_score is not None:
                    sentiment_diff = abs(message.sentiment_score - c.sentiment_score)
                    if sentiment_diff < 0.3:
                        context_data['relevance'] *= 1.1

                processed_contexts.append(context_data)

            # Sort by boosted relevance and return top contexts
            processed_contexts.sort(key=lambda x: x['relevance'], reverse=True)
            return processed_contexts[:limit]

        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}", exc_info=True)
            return []

# Add context cleanup task to main application
async def start_context_management():
    """Start the context management background tasks"""
    asyncio.create_task(cleanup_expired_contexts())
