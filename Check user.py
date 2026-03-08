from bcrypt import checkpw
from base64 import b64decode
import os

HASHED_PASSWORDS_FILE = 'Passwords.txt'

# Make sure the password file exists
if not os.path.exists(HASHED_PASSWORDS_FILE):
    print("No users found. Please add a user first.")
    exit()

# Get user input
user_name = input("Enter username: ")
password = input("Enter password: ")

# Flag to track if login succeeds
login_success = False

# Open the file and check credentials
with open(HASHED_PASSWORDS_FILE, "r") as password_file:
    for line in password_file:
        # Each line is in the format: base64username:hashed_password
        try:
            encoded_username, hashed_password = line.strip().split(":", 1)
        except ValueError:
            continue  # skip malformed lines

        decoded_username = b64decode(encoded_username.encode("utf-8")).decode("utf-8")

        if decoded_username == user_name:
            if checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
                login_success = True
            break  # stop checking after finding the user

if login_success:
    print(f"Login successful! Welcome {user_name}.")
else:
    print("Invalid username or password.")
