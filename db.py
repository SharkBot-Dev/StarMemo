import os
from pymongo import MongoClient
import dotenv

dotenv.load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["Users"]
memos_col = db["Memos"]
roles_col = db["Roles"]