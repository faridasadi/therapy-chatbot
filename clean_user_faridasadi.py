from database import get_db_session, delete_user_data
from models import User

def main():
    print("Starting data deletion for user 'faridasadi'...")
    
    with get_db_session() as db:
        try:
            # First verify if user exists
            user = db.query(User).filter(User.username == 'faridasadi').first()
            if not user:
                print("User 'faridasadi' not found in the database")
                return
            
            user_id = user.id
            print(f"Found user with ID: {user_id}")
            
            # Delete all user data using the comprehensive delete_user_data function
            success, message = delete_user_data(user_id, db)
            
            if success:
                # Explicitly commit the transaction after successful deletion
                db.commit()
                print(f"Delete data operation success: {success}")
                print("Verification message:", message)
                
                # Double check after commit
                remaining_user = db.query(User).filter(User.username == 'faridasadi').first()
                if remaining_user is None:
                    print("Final verification successful: User has been completely removed")
                else:
                    raise Exception("Warning: User still exists in the database after deletion")
            else:
                raise Exception(f"Deletion failed: {message}")
                
        except Exception as e:
            print(f"Error during deletion: {str(e)}")
            db.rollback()
            raise

if __name__ == "__main__":
    main()
