#!/usr/bin/env python3
"""
Script to add additional documents to the existing ChromaDB collection
"""
# Fix SQLite version for ChromaDB
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
from pathlib import Path
from dotenv import load_dotenv

import chromadb
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.rag import extract_article_info

# Load environment variables
load_dotenv()

# Constants
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
COLLECTION_NAME = "codigo_transito"
EMBEDDING_MODEL = "text-embedding-3-small"
PERSIST_DIR = "./chroma_db"


def get_embeddings_batch(client: OpenAI, texts: list) -> list:
    """Get embeddings for multiple texts in batch."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )
    return [item.embedding for item in response.data]


def load_and_chunk_document(file_path: str) -> list:
    """Load document and split into chunks."""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\nARTÍCULO", "\nCAPITULO", "\nTÍTULO", "\n\n", "\n", " "]
    )
    
    return splitter.split_text(text)


def add_document(file_path: str, doc_prefix: str):
    """Add a new document to the existing collection with article/section metadata."""
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    
    print(f"Current collection has {collection.count()} documents")
    
    # Load and chunk
    print(f"Loading and chunking: {file_path}")
    chunks = load_and_chunk_document(file_path)
    print(f"Created {len(chunks)} chunks")
    
    # Get existing count to create unique IDs
    existing_count = collection.count()
    
    # Track current article/title/chapter for context propagation
    current_title = None
    current_chapter = None
    current_article = None
    
    # Process in batches
    batch_size = 100
    total_indexed = 0
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_ids = [f"{doc_prefix}_chunk_{existing_count + i + j}" for j in range(len(batch))]
        
        # Extract metadata for each chunk
        batch_metadatas = []
        for j, chunk in enumerate(batch):
            extracted = extract_article_info(chunk)
            
            # Update current context if new info found
            if extracted["title"]:
                current_title = extracted["title"]
            if extracted["chapter"]:
                current_chapter = extracted["chapter"]
            if extracted["article"]:
                current_article = extracted["article"]
            
            # Use current context for chunks without explicit info
            # ChromaDB doesn't accept None values, so use empty string as fallback
            metadata = {
                "source": doc_prefix,
                "chunk_index": i + j,
                "article": extracted["article"] or current_article or "",
                "title": extracted["title"] or current_title or "",
                "chapter": extracted["chapter"] or current_chapter or "",
            }
            batch_metadatas.append(metadata)
        
        print(f"Embedding batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}...")
        embeddings = get_embeddings_batch(openai_client, batch)
        
        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch,
            metadatas=batch_metadatas
        )
        total_indexed += len(batch)
    
    print(f"Successfully indexed {total_indexed} chunks from {doc_prefix}")
    print(f"Collection now has {collection.count()} total documents")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python add_document.py <file_path> <doc_prefix>")
        print("Example: python add_document.py decreto_2106_2019.txt decreto_2106")
        sys.exit(1)
    
    file_path = sys.argv[1]
    doc_prefix = sys.argv[2]
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    add_document(file_path, doc_prefix)
