import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_db():
    global _client
    if _client is None:
        _client = MongoClient(os.getenv("MONGODB_URI"))
    return _client[os.getenv("MONGODB_DB_NAME", 
                              "healthcare_supply_chain")]

if __name__ == "__main__":
    db = get_db()
    print(" MongoDB connected:", db.list_collection_names())