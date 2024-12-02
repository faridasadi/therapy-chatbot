from database import get_db_session, delete_user_data
from models import User

def main():
    print("Starting data deletion for user 'faridasadi'...")
    
    # First query to get user's Telegram ID
    with get_db_session() as db:
        try:
            user = db.query(User).filter(User.username == 'faridasadi').first()
            if user:
                user_id = user.id
                print(f"Found user with ID: {user_id}")
                
                # Delete all user data
                success = delete_user_data(user_id, db)
                print(f"Delete data operation success: {success}")
                
                # Verify the deletion
                remaining_user = db.query(User).filter(User.username == 'faridasadi').first()
                if remaining_user is None:
                    print("Verification successful: User has been completely removed")
                else:
                    print("Warning: User still exists in the database")
            else:
                print("User 'faridasadi' not found in the database")
        except Exception as e:
            print(f"Error during deletion: {str(e)}")
            raise

if __name__ == "__main__":
    main()
