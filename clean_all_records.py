import logging
from sqlalchemy import text
from database import get_db_session
from models import User, Message, UserTheme, Subscription, MessageContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_all_records():
    """Clean all records from the database safely"""
    with get_db_session() as db:
        try:
            logger.info("Starting database cleanup...")
            
            # Define tables in order of deletion (respecting foreign key constraints)
            tables = [
                ('message_context', 'Message contexts'),
                ('message', 'Messages'),
                ('user_theme', 'User themes'),
                ('subscription', 'Subscriptions'),
                ('user', 'Users')
            ]
            
            # First, get initial record counts
            initial_counts = {}
            for table_name, description in tables:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                initial_counts[table_name] = count
                logger.info(f"Initial {description} count: {count}")
            
            # Delete records from each table with retry mechanism
            for table_name, description in tables:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Use an individual transaction for each table
                        db.execute(text("BEGIN"))
                        result = db.execute(text(f'DELETE FROM "{table_name}"'))
                        affected_rows = result.rowcount
                        db.execute(text("COMMIT"))
                        logger.info(f"Cleaned {affected_rows} {description} (Attempt {attempt + 1})")
                        break
                    except Exception as e:
                        db.execute(text("ROLLBACK"))
                        if attempt == max_retries - 1:
                            raise Exception(f"Failed to clean {description} after {max_retries} attempts: {str(e)}")
                        logger.warning(f"Retry cleaning {description}: {str(e)}")
                        continue
            
            # Verify the cleanup
            verification = {}
            for table_name, description in tables:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                verification[table_name] = count
                logger.info(f"Final {description} count: {count}")
            
            all_zero = all(count == 0 for count in verification.values())
            if all_zero:
                logger.info("Verification successful: All tables are empty")
                return True, "All records successfully deleted"
            else:
                remaining = {k: v for k, v in verification.items() if v > 0}
                return False, f"Some records remain: {remaining}"
            
        except Exception as e:
            error_msg = f"Error during database cleanup: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

if __name__ == "__main__":
    success, message = clean_all_records()
    if success:
        print("Database cleanup completed successfully")
    else:
        print(f"Database cleanup failed: {message}")
