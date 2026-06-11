import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_elastic():
    global _client
    if _client is None:
        _client = Elasticsearch(
            os.getenv("ELASTIC_ENDPOINT"),
            api_key=os.getenv("ELASTIC_API_KEY"),
            request_timeout=30
        )
    return _client

def ensure_index():
    client = get_elastic()
    index = os.getenv("ELASTIC_INDEX", "geopolitical-events")
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body={
            "mappings": {
                "properties": {
                    "event_type":  {"type": "keyword"},
                    "country":     {"type": "keyword"},
                    "severity":    {"type": "keyword"},
                    "description": {"type": "text"},
                    "timestamp":   {"type": "date"},
                    "keywords":    {"type": "keyword"}
                }
            }
        })
        print(f"Elastic index created: {index}")
    else:
        print(f"Elastic index exists: {index}")

if __name__ == "__main__":
    client = get_elastic()
    print(" Elastic connected:", 
          client.info()["version"]["number"])
    ensure_index()