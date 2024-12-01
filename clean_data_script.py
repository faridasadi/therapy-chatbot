import sys
from database import clean_user_data, get_db_session
from models import User, Message, UserTheme, Subscription
from datetime import datetime

def main():
    user_id = 63200096
    
    try:
        success = clean_user_data(user_id)
        if success:
            print(f"Successfully cleaned data for user {user_id}")
            sys.exit(0)
        else:
            print(f"Failed to clean data for user {user_id}")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
