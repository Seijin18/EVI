import os
import uuid
from typing import List, Dict, Any
from langchain_core.tools import tool
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "university_notes"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Initialize clients
qdrant_client = QdrantClient(url=QDRANT_URL)
embeddings_model = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)

# Ensure collection exists
try:
    if not qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
except Exception:
    pass

# Create langchain Qdrant vector store wrapper for easier search
vector_store = QdrantVectorStore(
    client=qdrant_client, collection_name=COLLECTION_NAME, embedding=embeddings_model
)


def extract_and_chunk_pdf(file_path: str) -> List[Dict[str, Any]]:
    """Load a PDF and split it into properly sized chunks."""
    loader = PyMuPDFLoader(file_path)
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
    chunks = text_splitter.split_documents(docs)
    return chunks


@tool
def ingest_university_pdf(file_path: str) -> str:
    """
    Ingest a single PDF file into the university notes knowledge base.
    Useful when a new file has been organized into the university folder.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        chunks = extract_and_chunk_pdf(file_path)
        if not chunks:
            return f"No text could be extracted from {file_path}"

        # Generate embeddings and upload
        vector_store.add_documents(chunks)

        return f"Successfully ingested {len(chunks)} chunks from {os.path.basename(file_path)}."
    except Exception as e:
        return f"Failed to ingest {file_path}: {str(e)}"


@tool
def query_university_notes(query: str, top_k: int = 3) -> str:
    """
    Search the university notes knowledge base for information matching the query.
    Useful for answering questions about lectures, syllabus, and study materials.
    """
    try:
        # Use langchain vector store for similarity search
        docs = vector_store.similarity_search(query, k=top_k)

        if not docs:
            return "No relevant notes found for your query."

        results = []
        for doc in docs:
            text = doc.page_content
            source = os.path.basename(doc.metadata.get("source", "Unknown"))
            page = doc.metadata.get("page", "Unknown")

            results.append(f"[Source: {source}, Page: {page}]\n{text}")

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Failed to query notes: {str(e)}"
