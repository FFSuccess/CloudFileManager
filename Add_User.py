from bcrypt import gensalt, hashpw
import os
from base64 import b64encode, b64decode
import uuid

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

# generate id
user_id = str(uuid.uuid4())

# Get file content of password file
with open(HASHED_PASSWORDS_FILE, "r") as password_file:
    password_file_content =  password_file.read()
user_password_list = password_file_content.split("\n")
username_list = []
user_id_list = []
for each_user in user_password_list:
    if each_user:
        base_64_username = each_user[:each_user.index(':')]
        username_list.append(b64decode(base_64_username).decode("utf-8"))
        each_user_id = each_user[each_user.rindex(':') + 1:]
        user_id_list.append(each_user_id)

# ensure unique id
while user_id in user_id_list:
    user_id = str(uuid.uuid4())

if user_name in username_list:
    print(f"User {user_name} already exists! User not added.")
    exit(0)

# Write to file
with open(HASHED_PASSWORDS_FILE, "a") as password_file:
    password_file.write(f"{encoded_username}:{hashed_password.decode('utf-8')}:{user_id}\n")

print(f"User {user_name} added successfully!")
