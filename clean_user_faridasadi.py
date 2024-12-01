from database import get_db_session, clean_user_data
from models import User

def main():
    print("Starting cleanup for user 'faridasadi'...")
    
    # First query to get user's Telegram ID
    with get_db_session() as db:
        try:
            user = db.query(User).filter(User.username == 'faridasadi').first()
            if user:
                user_id = user.id
                print(f"Found user with ID: {user_id}")
                
                # Clean the user data
                success = clean_user_data(user_id)
                print(f"Clean data operation success: {success}")
                
                # Verify the cleanup
                user = db.query(User).filter(User.username == 'faridasadi').first()
                print(f"Background completed status: {user.background_completed}")
                print(f"Messages count: {user.messages_count}")
                print(f"Weekly messages count: {user.weekly_messages_count}")
            else:
                print("User 'faridasadi' not found in the database")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
            raise

if __name__ == "__main__":
    main()
