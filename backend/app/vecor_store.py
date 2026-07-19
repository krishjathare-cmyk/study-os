import os

import chromadb
from dotenv import load_dotenv

load_dotenv()

STUDY_COLLECTION_NAME = "study_chunks"
ASSIGNMENT_COLLECTION_NAME = "assignments"


class VectorStoreError(Exception):
    pass


def _get_collection(collection_name: str = STUDY_COLLECTION_NAME):
    try:
        client = chromadb.CloudClient(
            api_key=os.getenv("CHROMA_API_KEY"),
            tenant=os.getenv("CHROMA_TENANT"),
            database=os.getenv("CHROMA_DATABASE"),
        )
        return client.get_or_create_collection(name=collection_name)
    except Exception as exc:
        raise VectorStoreError(f"Vector store setup failed: {exc}") from exc


def index_chunks(
    user_id: int,
    subject_id: int,
    document_id: int,
    filename: str,
    chunks: list[str],
    subtopic_ids: list[int | None] | None = None,
):
    ids = []
    documents = []
    metadatas = []

    if subtopic_ids is not None and len(subtopic_ids) != len(chunks):
        raise VectorStoreError("Each indexed chunk must have one subtopic ID.")

    for index, chunk_text in enumerate(chunks):
        chunk_id = f"user_{user_id}_subject_{subject_id}_doc_{document_id}_chunk_{index}"
        ids.append(chunk_id)
        documents.append(chunk_text)
        metadata = {
            "user_id": user_id,
            "subject_id": subject_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_index": index,
        }
        if subtopic_ids is not None and subtopic_ids[index] is not None:
            metadata["subtopic_id"] = subtopic_ids[index]
        metadatas.append(metadata)

    if not ids:
        return

    try:
        collection = _get_collection(STUDY_COLLECTION_NAME)
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    except Exception as exc:
        raise VectorStoreError(f"Failed to index chunks: {exc}") from exc


def delete_document_chunks(user_id: int, subject_id: int, document_id: int):
    try:
        collection = _get_collection(STUDY_COLLECTION_NAME)
        collection.delete(
            where={
                "$and": [
                    {"user_id": user_id},
                    {"subject_id": subject_id},
                    {"document_id": document_id},
                ]
            }
        )
    except Exception as exc:
        raise VectorStoreError(f"Failed to replace document chunks: {exc}") from exc


def retrieve_chunks(user_id: int, subject_id: int, query: str, top_k: int = 5):
    try:
        collection = _get_collection(STUDY_COLLECTION_NAME)
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"subject_id": subject_id},
                ]
            },
        )
    except Exception as exc:
        raise VectorStoreError(f"Failed to retrieve chunks: {exc}") from exc

    output = []
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for chunk_id, chunk_text, metadata, distance in zip(ids, documents, metadatas, distances):
        output.append(
            {
                "id": chunk_id,
                "chunk_text": chunk_text,
                "document_id": metadata.get("document_id"),
                "filename": metadata.get("filename"),
                "chunk_index": metadata.get("chunk_index"),
                "subtopic_id": metadata.get("subtopic_id"),
                "distance": distance,
            }
        )

    return output


def index_assignment_chunks(
    user_id: int,
    subject_id: int,
    assignment_id: int,
    filename: str,
    chunks: list[dict],
):
    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        node_ids = chunk.get("node_ids") or [0]
        for node_id in node_ids:
            ids.append(
                f"user_{user_id}_subject_{subject_id}_assignment_{assignment_id}_"
                f"chunk_{chunk['chunk_index']}_node_{node_id}"
            )
            documents.append(chunk["chunk_text"])
            metadatas.append(
                {
                    "user_id": user_id,
                    "subject_id": subject_id,
                    "assignment_id": assignment_id,
                    "assignment_chunk_id": chunk["id"],
                    "filename": filename,
                    "chunk_index": chunk["chunk_index"],
                    "subtopic_id": node_id,
                    "mapping_status": "mapped" if node_id else "unmapped",
                }
            )

    if not ids:
        return

    try:
        collection = _get_collection(ASSIGNMENT_COLLECTION_NAME)
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    except Exception as exc:
        raise VectorStoreError(f"Failed to index assignment chunks: {exc}") from exc


def delete_assignment_chunks(user_id: int, subject_id: int, assignment_id: int):
    try:
        collection = _get_collection(ASSIGNMENT_COLLECTION_NAME)
        collection.delete(
            where={
                "$and": [
                    {"user_id": user_id},
                    {"subject_id": subject_id},
                    {"assignment_id": assignment_id},
                ]
            }
        )
    except Exception as exc:
        raise VectorStoreError(f"Failed to replace assignment chunks: {exc}") from exc


def retrieve_assignment_chunks(
    user_id: int,
    subject_id: int,
    subtopic_ids: list[int],
    query: str,
    top_k: int = 5,
):
    if not subtopic_ids:
        return []

    try:
        collection = _get_collection(ASSIGNMENT_COLLECTION_NAME)
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"subject_id": subject_id},
                    {"subtopic_id": {"$in": subtopic_ids}},
                ]
            },
        )
    except Exception as exc:
        raise VectorStoreError(f"Failed to retrieve assignment chunks: {exc}") from exc

    output = []
    for chunk_id, chunk_text, metadata, distance in zip(
        results.get("ids", [[]])[0],
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
        results.get("distances", [[]])[0],
    ):
        output.append(
            {
                "id": chunk_id,
                "chunk_text": chunk_text,
                "assignment_id": metadata.get("assignment_id"),
                "assignment_chunk_id": metadata.get("assignment_chunk_id"),
                "filename": metadata.get("filename"),
                "chunk_index": metadata.get("chunk_index"),
                "subtopic_id": metadata.get("subtopic_id"),
                "distance": distance,
            }
        )
    return output
