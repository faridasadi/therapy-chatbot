import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
os.makedirs('static/logs', exist_ok=True)

class ErrorLogger:
    SEVERITY_LEVELS = {
        'CRITICAL': 50,
        'ERROR': 40,
        'WARNING': 30,
        'INFO': 20,
        'DEBUG': 10
    }

    # Rate limiting configuration
    ERROR_RATE_LIMIT = {
        'window_size': 60,  # 60 seconds
        'max_errors': 50,   # Maximum 50 errors per minute
        'error_counts': {},  # Track error counts by type
        'last_reset': datetime.utcnow()
    }

    def __init__(self):
        self.logger = logging.getLogger('telegram_bot')
        self.logger.setLevel(logging.DEBUG)

        # Create formatters
        json_formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s", "level":"%(levelname)s", "error_id":"%(error_id)s", '
            '"component":"%(component)s", "message":"%(message)s", "details":%(details)s}'
        )

        # Create handlers with improved rotation settings
        file_handler = RotatingFileHandler(
            'static/logs/telegram_bot/errors.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setFormatter(json_formatter)
        file_handler.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(json_formatter)
        console_handler.setLevel(logging.INFO)

        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def _generate_error_id(self, error: Exception) -> str:
        """Generate a unique error ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        error_hash = abs(hash(str(error)))
        return f"ERR-{timestamp}-{error_hash}"[:20]

    def _format_error_details(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format error details into a structured dictionary."""
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'stack_trace': traceback.format_exc(),
            'context': context or {}
        }
        return json.dumps(error_details)

    def _check_rate_limit(self, error_type: str) -> bool:
        """Check if error logging is within rate limits."""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.ERROR_RATE_LIMIT['window_size'])
        
        # Reset counts if window has passed
        if now - self.ERROR_RATE_LIMIT['last_reset'] > timedelta(seconds=self.ERROR_RATE_LIMIT['window_size']):
            self.ERROR_RATE_LIMIT['error_counts'] = {}
            self.ERROR_RATE_LIMIT['last_reset'] = now
        
        # Update error count
        count = self.ERROR_RATE_LIMIT['error_counts'].get(error_type, 0) + 1
        self.ERROR_RATE_LIMIT['error_counts'][error_type] = count
        
        return count <= self.ERROR_RATE_LIMIT['max_errors']

    def log_error(self, 
                  error: Exception, 
                  component: str, 
                  severity: str = 'ERROR',
                  context: Optional[Dict[str, Any]] = None) -> str:
        """
        Log an error with full context and details.
        
        Args:
            error: The exception object
            component: The component where the error occurred
            severity: Error severity level
            context: Additional context information
            
        Returns:
            str: The generated error ID
        """
        error_type = type(error).__name__
        
        # Skip logging if rate limit exceeded (except for CRITICAL errors)
        if severity != 'CRITICAL' and not self._check_rate_limit(error_type):
            return f"RATELIMITED-{self._generate_error_id(error)}"
        
        error_id = self._generate_error_id(error)
        
        # Enhance context with additional information
        enhanced_context = {
            'error_type': error_type,
            'error_count': self.ERROR_RATE_LIMIT['error_counts'].get(error_type, 1),
            'component_details': {
                'name': component,
                'timestamp': datetime.utcnow().isoformat()
            }
        }
        if context:
            enhanced_context.update(context)
            
        error_details = self._format_error_details(error, enhanced_context)
        
        log_level = self.SEVERITY_LEVELS.get(severity.upper(), logging.ERROR)
        
        extra = {
            'error_id': error_id,
            'component': component,
            'details': error_details
        }
        
        self.logger.log(log_level, str(error), extra=extra)
        return error_id

    def get_user_message(self, error_id: str, severity: str = 'ERROR') -> str:
        """Generate a user-friendly error message."""
        if severity == 'CRITICAL':
            return (
                f"I encountered a critical error (Ref: {error_id}). "
                "Our team has been notified and is working on it. "
                "Please try again later."
            )
        else:
            return (
                f"I apologize, but I encountered an error (Ref: {error_id}). "
                "You can:\n"
                "1. Try sending your message again\n"
                "2. Use /start to reset our conversation\n"
                "3. Contact support if the issue persists"
            )

# Create a global instance
error_logger = ErrorLogger()
