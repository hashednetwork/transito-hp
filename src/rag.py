"""
RAG Pipeline for Colombian Transit Code
Uses ChromaDB for vector storage and OpenAI embeddings
"""
# Fix SQLite version for ChromaDB
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
from pathlib import Path
from typing import List, Tuple

import chromadb
from chromadb.config import Settings
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Constants
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
COLLECTION_NAME = "codigo_transito"
EMBEDDING_MODEL = "text-embedding-3-small"


class RAGPipeline:
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Initialize RAG pipeline with ChromaDB and OpenAI."""
        self.persist_directory = persist_directory
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize ChromaDB with persistence
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text using OpenAI."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    
    def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts in batch."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    def load_and_chunk_document(self, file_path: str) -> List[str]:
        """Load document and split into chunks."""
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Use RecursiveCharacterTextSplitter for smart chunking
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\nARTÍCULO", "\nCAPITULO", "\nTÍTULO", "\n\n", "\n", " "]
        )
        
        chunks = splitter.split_text(text)
        return chunks
    
    def index_document(self, file_path: str, force_reindex: bool = False) -> int:
        """Index a document into ChromaDB. Returns number of chunks indexed."""
        # Check if already indexed
        if not force_reindex and self.collection.count() > 0:
            print(f"Collection already has {self.collection.count()} documents. Skipping indexing.")
            return self.collection.count()
        
        # Clear existing data if reindexing
        if force_reindex and self.collection.count() > 0:
            self.chroma_client.delete_collection(COLLECTION_NAME)
            self.collection = self.chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
        
        print(f"Loading and chunking document: {file_path}")
        chunks = self.load_and_chunk_document(file_path)
        print(f"Created {len(chunks)} chunks")
        
        # Process in batches of 100 (OpenAI limit for embeddings)
        batch_size = 100
        total_indexed = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_ids = [f"chunk_{i + j}" for j in range(len(batch))]
            
            print(f"Embedding batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}...")
            embeddings = self._get_embeddings_batch(batch)
            
            self.collection.add(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch,
                metadatas=[{"chunk_index": i + j} for j in range(len(batch))]
            )
            total_indexed += len(batch)
        
        print(f"Successfully indexed {total_indexed} chunks")
        return total_indexed
    
    def retrieve(self, query: str, n_results: int = 5) -> List[Tuple[str, float]]:
        """Retrieve top N relevant chunks for a query."""
        query_embedding = self._get_embedding(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "distances"]
        )
        
        # Return list of (document, distance) tuples
        documents = results['documents'][0] if results['documents'] else []
        distances = results['distances'][0] if results['distances'] else []
        
        return list(zip(documents, distances))
    
    def get_context_for_query(self, query: str, n_results: int = 5) -> str:
        """Get formatted context string for a query."""
        results = self.retrieve(query, n_results)
        
        if not results:
            return "No se encontraron artículos relevantes."
        
        context_parts = []
        for i, (doc, distance) in enumerate(results, 1):
            context_parts.append(f"--- Fragmento {i} ---\n{doc}")
        
        return "\n\n".join(context_parts)


def initialize_rag(document_path: str, persist_directory: str = "./chroma_db") -> RAGPipeline:
    """Initialize and index the RAG pipeline."""
    rag = RAGPipeline(persist_directory=persist_directory)
    rag.index_document(document_path)
    return rag


if __name__ == "__main__":
    # Test the RAG pipeline
    from dotenv import load_dotenv
    load_dotenv()
    
    rag = initialize_rag("codigo_transito.txt")
    
    # Test query
    query = "¿Cuál es la velocidad máxima permitida en zona escolar?"
    print(f"\nQuery: {query}")
    print("\nRelevant chunks:")
    for doc, dist in rag.retrieve(query):
        print(f"\n[Distance: {dist:.4f}]\n{doc[:300]}...")
