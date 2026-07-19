import os

import chromadb
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "study_chunks"

client = chromadb.CloudClient(
    api_key=os.getenv("CHROMA_API_KEY"),
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE")
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME
)


def index_chunks(
    user_id: int,
    subject_id: int,
    document_id: int,
    filename: str,
    chunks: list[str]
):
    ids = []
    documents = []
    metadatas = []

    for index, chunk_text in enumerate(chunks):
        chunk_id = f"user_{user_id}_subject_{subject_id}_doc_{document_id}_chunk_{index}"

        ids.append(chunk_id)
        documents.append(chunk_text)
        metadatas.append({
            "user_id": user_id,
            "subject_id": subject_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_index": index
        })

    if ids:
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )


def retrieve_chunks(
    subject_id: int,
    query: str,
    top_k: int = 5
):
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where={"subject_id": subject_id}
    )

    output = []

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for chunk_id, chunk_text, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances
    ):
        output.append({
            "id": chunk_id,
            "chunk_text": chunk_text,
            "document_id": metadata.get("document_id"),
            "filename": metadata.get("filename"),
            "chunk_index": metadata.get("chunk_index"),
            "distance": distance
        })

    return output