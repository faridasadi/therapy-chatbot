from typing import Optional, Dict, Any, Callable, Awaitable
from functools import wraps
import traceback
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from error_logging import error_logger

def handle_bot_error(error: Exception, update: Optional[Update] = None, context: Dict[str, Any] = None) -> str:
    """
    Centralized error handler for bot-related errors with enhanced context and recovery strategies.
    Returns the error_id for reference.
    """
    try:
        # Extract detailed error context
        error_context = {
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'update': update.to_dict() if update else None,
            'user_id': update.effective_user.id if update and update.effective_user else None,
            'chat_id': update.effective_chat.id if update and update.effective_chat else None,
            'message_id': update.message.message_id if update and update.message else None,
            'command': update.message.text if update and update.message else None,
            'additional_context': context or {}
        }

        # Determine severity and recovery strategy based on error type
        severity = 'ERROR'
        recovery_action = 'none'
        
        if isinstance(error, TelegramError):
            if 'Bad Request' in str(error):
                severity = 'WARNING'
                recovery_action = 'validate_input'
                error_context['recovery_hint'] = 'Input validation required'
            elif 'Forbidden' in str(error):
                severity = 'WARNING'
                recovery_action = 'block'
                error_context['recovery_hint'] = 'Bot was blocked by user'
            elif 'Conflict' in str(error):
                severity = 'WARNING'
                recovery_action = 'retry'
                error_context['recovery_hint'] = 'Retry after delay'
            else:
                severity = 'ERROR'
                recovery_action = 'report'
                error_context['recovery_hint'] = 'Manual intervention may be required'
        
        error_context['recovery_action'] = recovery_action
        
        # Enhanced error logging with severity assessment
        error_id = error_logger.log_error(
            error=error,
            component='telegram_bot',
            severity=severity,
            context=error_context
        )
        
        # Log additional diagnostic information for critical errors
        if severity == 'ERROR':
            print(f"Critical Telegram Bot Error (ID: {error_id}):")
            print(f"Type: {error_context['error_type']}")
            print(f"Message: {error_context['error_message']}")
            print(f"Recovery Action: {recovery_action}")
        
        return error_id
        
    except Exception as logging_error:
        # Fallback error logging if the main error handling fails
        fallback_error_id = error_logger.log_error(
            error=logging_error,
            component='error_handler',
            severity='CRITICAL',
            context={
                'original_error': str(error),
                'handler_error': str(logging_error),
                'handler_state': 'failed'
            }
        )
        print(f"Critical error in error handler (ID: {fallback_error_id})")
        return fallback_error_id

def bot_error_handler(f: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """
    Decorator for handling errors in bot command handlers.
    """
    @wraps(f)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await f(self, update, context, *args, **kwargs)
        except Exception as e:
            error_id = handle_bot_error(e, update, {
                'handler': f.__name__,
                'args': str(args),
                'kwargs': str(kwargs)
            })
            
            if update and update.effective_message:
                error_message = error_logger.get_user_message(error_id)
                try:
                    await update.effective_message.reply_text(error_message)
                except:
                    # If we can't send the detailed error message, try a simple one
                    try:
                        await update.effective_message.reply_text(
                            "An error occurred. Please try again later."
                        )
                    except:
                        pass  # If we can't send any message, silently fail
            
            # Re-raise critical errors
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
    
    return wrapper

def handle_web_error(error: Exception, request_info: Optional[Dict[str, Any]] = None) -> str:
    """
    Centralized error handler for web-related errors.
    Returns the error_id for reference.
    """
    error_context = {
        'timestamp': datetime.utcnow().isoformat(),
        'request_info': request_info or {},
        'traceback': traceback.format_exc()
    }
    
    severity = 'ERROR'
    component = 'web_api'
    
    # Log the error with our error logging system
    error_id = error_logger.log_error(
        error=error,
        component=component,
        severity=severity,
        context=error_context
    )
    
    return error_id

def web_error_handler(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for handling errors in web API endpoints.
    """
    @wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            error_id = handle_web_error(e, {
                'handler': f.__name__,
                'args': str(args),
                'kwargs': str(kwargs)
            })
            
            # Return a JSON error response
            return {
                'error': True,
                'error_id': error_id,
                'message': 'An error occurred while processing your request'
            }, 500
    
    return wrapper
