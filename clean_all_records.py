from database import get_db_session
from models import User, Message, UserTheme, Subscription, MessageContext
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_all_records():
    """Clean all records from all tables in the database with proper constraint handling"""
    with get_db_session() as db:
        try:
            logger.info("Starting database cleanup...")
            
            # Begin transaction and disable triggers
            db.execute(text("BEGIN"))
            db.execute(text("SET session_replication_role = 'replica'"))
            
            # Drop all foreign key constraints temporarily
            logger.info("Temporarily disabling foreign key constraints...")
            db.execute(text("""
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT conname, conrelid::regclass AS table_name FROM pg_constraint WHERE contype = 'f') LOOP
                        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.table_name, r.conname);
                    END LOOP;
                END $$;
            """))
            
            # Truncate each table individually in reverse dependency order
            logger.info("Starting database truncation...")
            tables = ['message_context', 'message', 'user_theme', 'subscription', 'user']
            for table in tables:
                db.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
                logger.info(f"Truncated table {table}")
            
            # Re-create foreign key constraints
            logger.info("Re-creating foreign key constraints...")
            db.execute(text("""
                ALTER TABLE message_context
                ADD CONSTRAINT message_context_message_id_fkey 
                FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE;
                
                ALTER TABLE message
                ADD CONSTRAINT message_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES "user"(id);
                
                ALTER TABLE user_theme
                ADD CONSTRAINT user_theme_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES "user"(id);
                
                ALTER TABLE subscription
                ADD CONSTRAINT subscription_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES "user"(id);
            """))
            
            # Re-enable triggers
            db.execute(text("SET session_replication_role = 'origin'"))
            
            # Commit the transaction
            db.commit()
            logger.info("Successfully cleaned all records from the database")
            
            # Verify the cleanup
            verification = {}
            tables = ['message_context', 'message', 'user_theme', 'subscription', 'user']
            for table in tables:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                verification[table] = count
                
            all_zero = all(count == 0 for count in verification.values())
            if all_zero:
                logger.info("Verification successful: All tables are empty")
                return True, "All records successfully deleted"
            else:
                remaining = {k: v for k, v in verification.items() if v > 0}
                return False, f"Some records remain: {remaining}"
                
        except Exception as e:
            db.rollback()
            error_msg = f"Error during database cleanup: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

if __name__ == "__main__":
    success, message = clean_all_records()
    if success:
        print("Database cleanup completed successfully")
    else:
        print(f"Database cleanup failed: {message}")
