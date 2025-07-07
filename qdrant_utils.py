from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)
import hashlib, os

COLLECTION_NAME = "chat_history"

def init_qdrant():
    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    collections = client.get_collections().collections

    if COLLECTION_NAME not in [c.name for c in collections]:
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
        )

    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="session",
            field_schema="keyword"
        )
    except Exception: pass

    return client

def save_to_qdrant(user_input, assistant_response, session_name, client):
    pt = PointStruct(
        id=int(hashlib.sha256((session_name + user_input).encode()).hexdigest(), 16) % (10**18),
        vector=[0.0] * 1536,
        payload={"role": "assistant", "content": assistant_response, "session": session_name}
    )
    client.upsert(collection_name=COLLECTION_NAME, points=[pt])

def get_sessions(client):
    res = client.scroll(collection_name=COLLECTION_NAME, limit=100, with_payload=True)
    return list({pt.payload["session"] for pt in res.points if "session" in pt.payload})

def get_session_history(client, session_name):
    flt = Filter(must=[FieldCondition(key="session", match=MatchValue(value=session_name))])
    res = client.scroll(collection_name=COLLECTION_NAME, limit=100, with_payload=True, filter=flt)
    messages = [{"role": pt.payload["role"], "content": pt.payload["content"]} for pt in res.points]
    return messages

def delete_session(client, session_name):
    flt = Filter(must=[FieldCondition(key="session", match=MatchValue(value=session_name))])
    client.delete(collection_name=COLLECTION_NAME, points_selector=flt)
