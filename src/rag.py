"""
Enhanced RAG Pipeline for Colombian Transit Code
Multi-document indexing with ChromaDB and OpenAI embeddings
Supports: Legal codes, decrees, guides, jurisprudence
"""
# Fix SQLite version for ChromaDB
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
import re
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from datetime import datetime

import chromadb
from chromadb.config import Settings
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Configure logging
logger = logging.getLogger(__name__)

# Constants
CHUNK_SIZE = 1000  # Increased for better context
CHUNK_OVERLAP = 200
COLLECTION_NAME = "transito_colombia_v2"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Document source metadata - for citation and display
# Priority: 1 = highest (laws, constitution), 2 = medium (decrees, jurisprudence), 3 = lower (guides)
SOURCE_METADATA = {
    "codigo_transito": {
        "name": "Ley 769 de 2002 (Código Nacional de Tránsito Terrestre)",
        "type": "ley",
        "priority": 1,
        "year": 2002,
        "official_source": "Secretaría del Senado",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5557"
    },
    "decreto_2106": {
        "name": "Decreto 2106 de 2019 (Simplificación de Trámites)",
        "type": "decreto",
        "priority": 2,
        "year": 2019,
        "official_source": "Función Pública",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=103352"
    },
    "decreto_1079": {
        "name": "Decreto 1079 de 2015 (Decreto Único Reglamentario Transporte)",
        "type": "decreto",
        "priority": 2,
        "year": 2015,
        "official_source": "Ministerio de Transporte",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=77889"
    },
    "ley_1843": {
        "name": "Ley 1843 de 2017 (Fotodetección de Infracciones)",
        "type": "ley",
        "priority": 1,
        "year": 2017,
        "official_source": "Secretaría del Senado",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=82815"
    },
    "compendio_normativo": {
        "name": "Compendio Normativo de Tránsito 2024-2025",
        "type": "compendio",
        "priority": 1,
        "year": 2025,
        "official_source": "Compilación actualizada"
    },
    "inventario_documentos": {
        "name": "Inventario de Documentos Oficiales y Jerarquía Normativa",
        "type": "referencia",
        "priority": 2,
        "year": 2025,
        "official_source": "Guía de fuentes oficiales"
    },
    "senorbiter": {
        "name": "Guías Prácticas Señor Biter",
        "type": "guia",
        "priority": 3,
        "year": 2024,
        "official_source": "senorbiter.com - Educador en derechos de conductores"
    },
    "jurisprudencia": {
        "name": "Jurisprudencia Constitucional",
        "type": "jurisprudencia",
        "priority": 2,
        "year": 2020,
        "official_source": "Corte Constitucional / Consejo de Estado"
    },
    "resolucion_compilatoria": {
        "name": "Resolución 20223040045295 de 2022 (Resolución Única Compilatoria)",
        "type": "resolucion",
        "priority": 2,
        "year": 2022,
        "official_source": "Ministerio de Transporte"
    },
    "manual_senalizacion": {
        "name": "Manual de Señalización Vial de Colombia 2024 (Anexo 76)",
        "type": "manual",
        "priority": 2,
        "year": 2024,
        "official_source": "Ministerio de Transporte",
        "nota": "Adoptado por Res. 20243040045005. Fe de erratas: Res. 20253040002075"
    },
    "manual_senalizacion_2015": {
        "name": "Manual de Señalización Vial 2015 (histórico)",
        "type": "manual",
        "priority": 3,
        "year": 2015,
        "official_source": "Ministerio de Transporte",
        "nota": "Reemplazado por Manual 2024. Mantener para consultas retroactivas."
    },
    "ley_2251": {
        "name": "Ley 2251 de 2022 (Ley Julián Esteban - Velocidad)",
        "type": "ley",
        "priority": 1,
        "year": 2022,
        "official_source": "Función Pública",
        "nota": "Modifica Arts. 106-107 Código de Tránsito (velocidad)"
    },
    "pnsv_2022": {
        "name": "Decreto 1430 de 2022 (Plan Nacional de Seguridad Vial 2022-2031)",
        "type": "decreto",
        "priority": 2,
        "year": 2022,
        "official_source": "DAPRE / MinTransporte",
        "nota": "Marco de política Sistema Seguro"
    },
    "resolucion_velocidad": {
        "name": "Resolución 20233040025995 de 2023 (Metodología Velocidad)",
        "type": "resolucion",
        "priority": 2,
        "year": 2023,
        "official_source": "MinTransporte / ANSV"
    },
    "resolucion_cascos": {
        "name": "Resolución 20203040023385 de 2020 (Condiciones Uso Casco)",
        "type": "resolucion",
        "priority": 2,
        "year": 2020,
        "official_source": "MinTransporte"
    },
    "resolucion_sast": {
        "name": "Resolución 20203040011245 de 2020 (Criterios Técnicos SAST/Fotodetección)",
        "type": "resolucion",
        "priority": 2,
        "year": 2020,
        "official_source": "MinTransporte",
        "nota": "Clave para legalidad de fotodetección. Se articula con Ley 1843 y Decreto 2106."
    },
    "resolucion_pesv": {
        "name": "Resolución 20223040040595 de 2022 (Metodología PESV)",
        "type": "resolucion",
        "priority": 2,
        "year": 2022,
        "official_source": "MinTransporte",
        "nota": "Deroga Res. 1565/2014. Obligatoria para organizaciones con PESV."
    },
    "concepto_fotomultas": {
        "name": "Concepto Sala de Consulta Rad. 2433 de 2020 (Fotomultas)",
        "type": "jurisprudencia",
        "priority": 2,
        "year": 2020,
        "official_source": "Consejo de Estado",
        "nota": "Doctrina orientadora sobre participación privada en fotomultas."
    },
    "circular_plan365": {
        "name": "Circular Conjunta 023 de 2025 (Plan 365)",
        "type": "circular",
        "priority": 3,
        "year": 2025,
        "official_source": "MinTransporte + ANSV + Supertransporte + DITRA"
    },
    "circular_sast": {
        "name": "Circular Externa 20254000000867 (SAST y Control Señalización)",
        "type": "circular",
        "priority": 3,
        "year": 2025,
        "official_source": "Superintendencia de Transporte"
    },
    "constitucion": {
        "name": "Constitución Política de Colombia 1991",
        "type": "constitucion",
        "priority": 1,
        "year": 1991,
        "official_source": "DAPRE / Secretaría del Senado",
        "url": "https://www.secretariasenado.gov.co/constitucion-politica"
    }
}


def extract_metadata_from_text(text: str, source_id: str) -> Dict[str, Optional[str]]:
    """
    Extract rich metadata from a text chunk including article, chapter, title, sentencia.
    Enhanced for Colombian legal documents.
    """
    info = {
        "article": None,
        "title": None,
        "chapter": None,
        "sentencia": None,
        "ley": None,
        "decreto": None,
        "section": None
    }
    
    # Pattern for articles: "Artículo 123" or "ARTÍCULO 123"
    article_pattern = r'[Aa]rt[íi]culo\.?\s*(\d+[A-Za-z]?)[\.\-\s:]'
    article_match = re.search(article_pattern, text)
    if article_match:
        info["article"] = f"Artículo {article_match.group(1)}"
    
    # Pattern for titles: "TÍTULO I" or "Título II"
    title_pattern = r'T[ÍI]TULO\s+([IVXLCDM]+|[\d]+)[\.\-\s]*([^\n]*)?'
    title_match = re.search(title_pattern, text, re.IGNORECASE)
    if title_match:
        title_num = title_match.group(1)
        title_name = title_match.group(2).strip() if title_match.group(2) else ""
        info["title"] = f"Título {title_num}" + (f" - {title_name}" if title_name else "")
    
    # Pattern for chapters: "CAPÍTULO I"
    chapter_pattern = r'CAP[ÍI]TULO\s+([IVXLCDM]+|[\d]+)[\.\-\s]*([^\n]*)?'
    chapter_match = re.search(chapter_pattern, text, re.IGNORECASE)
    if chapter_match:
        chap_num = chapter_match.group(1)
        chap_name = chapter_match.group(2).strip() if chapter_match.group(2) else ""
        info["chapter"] = f"Capítulo {chap_num}" + (f" - {chap_name}" if chap_name else "")
    
    # Pattern for sentencias: "C-530 de 2003" or "Sentencia C-038 de 2020"
    sentencia_pattern = r'(?:Sentencia\s+)?([CTSU]-\d+)\s+de\s+(\d{4})'
    sentencia_match = re.search(sentencia_pattern, text, re.IGNORECASE)
    if sentencia_match:
        info["sentencia"] = f"Sentencia {sentencia_match.group(1)} de {sentencia_match.group(2)}"
    
    # Pattern for laws: "Ley 769 de 2002"
    ley_pattern = r'Ley\s+(\d+)\s+de\s+(\d{4})'
    ley_match = re.search(ley_pattern, text, re.IGNORECASE)
    if ley_match:
        info["ley"] = f"Ley {ley_match.group(1)} de {ley_match.group(2)}"
    
    # Pattern for decrees: "Decreto 2106 de 2019"
    decreto_pattern = r'Decreto\s+(\d+)\s+de\s+(\d{4})'
    decreto_match = re.search(decreto_pattern, text, re.IGNORECASE)
    if decreto_match:
        info["decreto"] = f"Decreto {decreto_match.group(1)} de {decreto_match.group(2)}"
    
    # Section headers (common in guides)
    section_pattern = r'^[=]+\n([^\n=]+)\n[=]+'
    section_match = re.search(section_pattern, text, re.MULTILINE)
    if section_match:
        info["section"] = section_match.group(1).strip()
    
    return info


def format_reference(metadata: Dict) -> str:
    """Format metadata into a readable reference string for display."""
    parts = []
    
    # Source document name
    source = metadata.get("source", "")
    source_info = SOURCE_METADATA.get(source, {})
    source_name = source_info.get("name", source)
    if source_name:
        parts.append(f"📖 {source_name}")
    
    # Sentencia (highest priority for jurisprudence)
    if metadata.get("sentencia"):
        parts.append(f"⚖️ {metadata['sentencia']}")
    
    # Article
    if metadata.get("article"):
        parts.append(f"📌 {metadata['article']}")
    
    # Law or Decree reference
    if metadata.get("ley") and "Ley" not in source_name:
        parts.append(f"📜 {metadata['ley']}")
    if metadata.get("decreto") and "Decreto" not in source_name:
        parts.append(f"📋 {metadata['decreto']}")
    
    # Chapter/Title
    if metadata.get("chapter"):
        parts.append(f"📂 {metadata['chapter']}")
    elif metadata.get("title"):
        parts.append(f"📂 {metadata['title']}")
    elif metadata.get("section"):
        parts.append(f"📂 {metadata['section']}")
    
    return " | ".join(parts) if parts else "Referencia general"


def compute_chunk_hash(text: str) -> str:
    """Compute a hash for a text chunk for deduplication."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


class RAGPipeline:
    """
    Enhanced RAG Pipeline for Colombian Transit Law.
    Features:
    - Multi-document indexing with source tracking
    - Rich metadata extraction for citations
    - Hybrid search with relevance scoring
    - Configurable chunking strategies
    """
    
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
        
        # Track indexed documents
        self._index_state_file = Path(persist_directory) / "index_state.json"
        self._index_state = self._load_index_state()
        
        logger.info(f"RAG Pipeline initialized. Collection has {self.collection.count()} documents.")
    
    def _load_index_state(self) -> Dict[str, Any]:
        """Load index state from disk."""
        if self._index_state_file.exists():
            try:
                with open(self._index_state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load index state: {e}")
        return {"indexed_files": {}, "last_update": None}
    
    def _save_index_state(self):
        """Save index state to disk."""
        self._index_state["last_update"] = datetime.now().isoformat()
        try:
            with open(self._index_state_file, 'w') as f:
                json.dump(self._index_state, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save index state: {e}")
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text using OpenAI."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    
    def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts in batch."""
        # OpenAI has a limit, process in sub-batches if needed
        max_batch = 100
        all_embeddings = []
        
        for i in range(0, len(texts), max_batch):
            batch = texts[i:i + max_batch]
            response = self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch
            )
            all_embeddings.extend([item.embedding for item in response.data])
        
        return all_embeddings
    
    def _create_text_splitter(self, doc_type: str = "legal") -> RecursiveCharacterTextSplitter:
        """Create appropriate text splitter based on document type."""
        if doc_type in ["ley", "decreto"]:
            # Legal documents: split on article boundaries
            separators = [
                "\nARTÍCULO", "\nArtículo",
                "\nCAPÍTULO", "\nCapítulo",
                "\nTÍTULO", "\nTítulo",
                "\nPARÁGRAFO", "\nParágrafo",
                "\n\n", "\n", ". ", " "
            ]
        elif doc_type == "guia":
            # Guides: split on section boundaries
            separators = [
                "\n================", "\n===",
                "\n\n\n", "\n\n", "\n", ". ", " "
            ]
        elif doc_type == "jurisprudencia":
            # Jurisprudence: split on case boundaries
            separators = [
                "\nSentencia", "\nSENTENCIA",
                "\nCONSIDERANDO", "\nRESUELVE",
                "\n\n", "\n", ". ", " "
            ]
        else:
            # Default
            separators = ["\n\n", "\n", ". ", " "]
        
        return RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=separators,
            length_function=len
        )
    
    def load_and_chunk_document(
        self, 
        file_path: str, 
        source_id: str,
        doc_type: str = "legal"
    ) -> List[Tuple[str, Dict]]:
        """
        Load document and split into chunks with metadata.
        Returns list of (chunk_text, metadata) tuples.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        splitter = self._create_text_splitter(doc_type)
        chunks = splitter.split_text(text)
        
        # Enrich each chunk with metadata
        enriched_chunks = []
        for i, chunk in enumerate(chunks):
            # Extract metadata from chunk content
            extracted_meta = extract_metadata_from_text(chunk, source_id)
            
            # Build full metadata
            source_info = SOURCE_METADATA.get(source_id, {})
            metadata = {
                "source": source_id,
                "source_name": source_info.get("name", source_id),
                "source_type": source_info.get("type", "unknown"),
                "source_priority": source_info.get("priority", 5),
                "chunk_index": i,
                "chunk_hash": compute_chunk_hash(chunk),
                "indexed_at": datetime.now().isoformat(),
                **{k: v for k, v in extracted_meta.items() if v is not None}
            }
            
            enriched_chunks.append((chunk, metadata))
        
        return enriched_chunks
    
    def index_document(
        self, 
        file_path: str, 
        source_id: str,
        force_reindex: bool = False
    ) -> int:
        """
        Index a single document into ChromaDB.
        Returns number of chunks indexed.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return 0
        
        # Check if already indexed (by file hash)
        file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
        indexed_info = self._index_state.get("indexed_files", {}).get(str(file_path), {})
        
        if not force_reindex and indexed_info.get("hash") == file_hash:
            logger.info(f"Document already indexed (hash match): {file_path.name}")
            return indexed_info.get("chunk_count", 0)
        
        # Get document type from source metadata
        source_info = SOURCE_METADATA.get(source_id, {})
        doc_type = source_info.get("type", "legal")
        
        logger.info(f"Indexing document: {file_path.name} (source: {source_id}, type: {doc_type})")
        
        # Load and chunk
        chunks_with_meta = self.load_and_chunk_document(file_path, source_id, doc_type)
        logger.info(f"Created {len(chunks_with_meta)} chunks")
        
        if not chunks_with_meta:
            return 0
        
        # Delete old chunks from this source if reindexing
        if force_reindex or indexed_info:
            try:
                # Get IDs of existing chunks from this source
                existing = self.collection.get(
                    where={"source": source_id},
                    include=[]
                )
                if existing and existing['ids']:
                    self.collection.delete(ids=existing['ids'])
                    logger.info(f"Deleted {len(existing['ids'])} old chunks from source {source_id}")
            except Exception as e:
                logger.warning(f"Could not delete old chunks: {e}")
        
        # Process and index in batches
        batch_size = 50
        total_indexed = 0
        
        for i in range(0, len(chunks_with_meta), batch_size):
            batch = chunks_with_meta[i:i + batch_size]
            texts = [c[0] for c in batch]
            metadatas = [c[1] for c in batch]
            ids = [f"{source_id}_{m['chunk_hash']}" for _, m in batch]
            
            logger.info(f"Embedding batch {i // batch_size + 1}/{(len(chunks_with_meta) - 1) // batch_size + 1}...")
            embeddings = self._get_embeddings_batch(texts)
            
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            total_indexed += len(batch)
        
        # Update index state
        self._index_state.setdefault("indexed_files", {})[str(file_path)] = {
            "hash": file_hash,
            "source_id": source_id,
            "chunk_count": total_indexed,
            "indexed_at": datetime.now().isoformat()
        }
        self._save_index_state()
        
        logger.info(f"Successfully indexed {total_indexed} chunks from {file_path.name}")
        return total_indexed
    
    def index_all_documents(self, documents_config: List[Dict], force_reindex: bool = False) -> int:
        """
        Index multiple documents from a configuration list.
        Config format: [{"path": "file.txt", "source_id": "codigo_transito"}, ...]
        """
        total = 0
        for doc in documents_config:
            count = self.index_document(
                doc["path"], 
                doc["source_id"],
                force_reindex=force_reindex
            )
            total += count
        
        logger.info(f"Total indexed: {total} chunks from {len(documents_config)} documents")
        return total
    
    def retrieve(
        self, 
        query: str, 
        n_results: int = 5,
        source_filter: Optional[List[str]] = None,
        min_relevance: float = 0.0
    ) -> List[Tuple[str, float, Dict]]:
        """
        Retrieve top N relevant chunks for a query with metadata.
        
        Args:
            query: Search query
            n_results: Maximum results to return
            source_filter: Optional list of source_ids to filter by
            min_relevance: Minimum relevance score (0-1, higher is better)
            
        Returns:
            List of (document, relevance_score, metadata) tuples
        """
        query_embedding = self._get_embedding(query)
        
        # Build where clause for filtering
        where = None
        if source_filter:
            where = {"source": {"$in": source_filter}}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results * 2,  # Get more, filter later
            where=where,
            include=["documents", "distances", "metadatas"]
        )
        
        if not results['documents'] or not results['documents'][0]:
            return []
        
        documents = results['documents'][0]
        distances = results['distances'][0]
        metadatas = results['metadatas'][0]
        
        # Convert distance to relevance score (cosine distance -> similarity)
        # ChromaDB returns distance, lower is better. Convert to similarity.
        enriched_results = []
        for doc, dist, meta in zip(documents, distances, metadatas):
            # Cosine distance to similarity: similarity = 1 - distance
            relevance = 1 - dist
            
            # Apply minimum relevance filter
            if relevance < min_relevance:
                continue
            
            # Boost by source priority
            priority = meta.get("source_priority", 5)
            boosted_relevance = relevance * (1 + (5 - priority) * 0.05)
            
            enriched_results.append((doc, boosted_relevance, meta))
        
        # Sort by boosted relevance and take top n_results
        enriched_results.sort(key=lambda x: x[1], reverse=True)
        return enriched_results[:n_results]
    
    def get_context_for_query(
        self, 
        query: str, 
        n_results: int = 5,
        include_references: bool = True
    ) -> str:
        """
        Get formatted context string for LLM with references.
        """
        results = self.retrieve(query, n_results)
        
        if not results:
            return "No se encontraron artículos o normas relevantes en la base de datos."
        
        context_parts = []
        seen_content = set()  # Deduplicate similar chunks
        
        for i, (doc, relevance, metadata) in enumerate(results, 1):
            # Simple dedup by first 100 chars
            content_key = doc[:100]
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            
            if include_references:
                reference = format_reference(metadata)
                relevance_pct = int(relevance * 100)
                context_parts.append(
                    f"--- Fragmento {i} (Relevancia: {relevance_pct}%) ---\n"
                    f"{reference}\n\n{doc}"
                )
            else:
                context_parts.append(f"--- Fragmento {i} ---\n{doc}")
        
        return "\n\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the indexed documents."""
        total_docs = self.collection.count()
        
        # Get counts by source
        source_counts = {}
        for source_id in SOURCE_METADATA.keys():
            try:
                result = self.collection.get(
                    where={"source": source_id},
                    include=[]
                )
                source_counts[source_id] = len(result['ids']) if result['ids'] else 0
            except:
                source_counts[source_id] = 0
        
        return {
            "total_chunks": total_docs,
            "by_source": source_counts,
            "index_state": self._index_state,
            "collection_name": COLLECTION_NAME,
            "embedding_model": EMBEDDING_MODEL
        }


def get_default_documents_config(base_path: str = ".") -> List[Dict]:
    """Get default document configuration for indexing."""
    base = Path(base_path)
    
    configs = []
    
    # Main legal documents - ordered by priority
    doc_mappings = [
        # Primary sources (laws and codes)
        ("codigo_transito.txt", "codigo_transito"),
        ("decreto_2106_2019.txt", "decreto_2106"),
        # Compendiums and reference
        ("docs/compendio_normativo.txt", "compendio_normativo"),
        ("docs/inventario_documentos.txt", "inventario_documentos"),
        # Practical guides
        ("senorbiter_guias.txt", "senorbiter"),
    ]
    
    for filename, source_id in doc_mappings:
        path = base / filename
        if path.exists():
            configs.append({"path": str(path), "source_id": source_id})
            logger.debug(f"Found document: {filename} -> {source_id}")
        else:
            logger.debug(f"Document not found (optional): {filename}")
    
    return configs


def initialize_rag(
    base_path: str = ".", 
    persist_directory: str = "./chroma_db",
    force_reindex: bool = False
) -> RAGPipeline:
    """Initialize and index the RAG pipeline with all available documents."""
    rag = RAGPipeline(persist_directory=persist_directory)
    
    # Get documents to index
    docs_config = get_default_documents_config(base_path)
    
    if docs_config:
        logger.info(f"Found {len(docs_config)} documents to index")
        rag.index_all_documents(docs_config, force_reindex=force_reindex)
    else:
        logger.warning("No documents found to index!")
    
    return rag


if __name__ == "__main__":
    # Test the RAG pipeline
    import logging
    logging.basicConfig(level=logging.INFO)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Initializing RAG pipeline...")
    rag = initialize_rag(force_reindex=True)
    
    print("\n📊 Index Statistics:")
    stats = rag.get_stats()
    print(f"Total chunks: {stats['total_chunks']}")
    for source, count in stats['by_source'].items():
        if count > 0:
            print(f"  - {source}: {count} chunks")
    
    # Test queries
    test_queries = [
        "¿Cuál es la velocidad máxima permitida en zona escolar?",
        "¿Cómo tumbar una fotomulta?",
        "¿Las multas de tránsito prescriben?",
        "¿Qué dice la Sentencia C-038 de 2020?",
        "¿Me pueden exigir documentos físicos en un retén?"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: {query}")
        print("-" * 50)
        results = rag.retrieve(query, n_results=2)
        for doc, score, meta in results:
            print(f"[{score:.2f}] {format_reference(meta)}")
            print(f"    {doc[:150]}...")
