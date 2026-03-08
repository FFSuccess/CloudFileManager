from bcrypt import gensalt, hashpw
import os
from base64 import b64encode

# Get user input
user_name = input("Give user name to add: ")
password = input("Give password to use: ")
input(f"Are you sure you want to add user called {user_name} with password: {password}? (Press Enter to continue)")

HASHED_PASSWORDS_FILE = 'Passwords.txt'

# Ensure the file exists
if not os.path.exists(HASHED_PASSWORDS_FILE):
    with open(HASHED_PASSWORDS_FILE, "w+") as password_file:
        pass

# Hash the password
hashed_password = hashpw(password.encode("utf-8"), gensalt())

# Encode the username in base64
encoded_username = b64encode(user_name.encode("utf-8")).decode("utf-8")

# Write to file
with open(HASHED_PASSWORDS_FILE, "a") as password_file:
    password_file.write(f"{encoded_username}:{hashed_password.decode('utf-8')}\n")

print(f"User {user_name} added successfully!")
