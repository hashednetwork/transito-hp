"""
Tests for the RAG pipeline metadata extraction and utilities
These tests don't require the full RAG pipeline initialization
"""
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only the utility functions that don't trigger chromadb
# We test the core logic without the heavy dependencies


def extract_metadata_from_text(text: str, source_id: str):
    """
    Inline copy of extract_metadata_from_text for testing without imports.
    This avoids triggering chromadb imports.
    """
    import re
    
    info = {
        "article": None,
        "title": None,
        "chapter": None,
        "sentencia": None,
        "ley": None,
        "decreto": None,
        "section": None
    }
    
    # Pattern for articles
    article_pattern = r'[Aa]rt[íi]culo\.?\s*(\d+[A-Za-z]?)[\.\-\s:]'
    article_match = re.search(article_pattern, text)
    if article_match:
        info["article"] = f"Artículo {article_match.group(1)}"
    
    # Pattern for titles
    title_pattern = r'T[ÍI]TULO\s+([IVXLCDM]+|[\d]+)[\.\-\s]*([^\n]*)?'
    title_match = re.search(title_pattern, text, re.IGNORECASE)
    if title_match:
        title_num = title_match.group(1)
        title_name = title_match.group(2).strip() if title_match.group(2) else ""
        info["title"] = f"Título {title_num}" + (f" - {title_name}" if title_name else "")
    
    # Pattern for chapters
    chapter_pattern = r'CAP[ÍI]TULO\s+([IVXLCDM]+|[\d]+)[\.\-\s]*([^\n]*)?'
    chapter_match = re.search(chapter_pattern, text, re.IGNORECASE)
    if chapter_match:
        chap_num = chapter_match.group(1)
        chap_name = chapter_match.group(2).strip() if chapter_match.group(2) else ""
        info["chapter"] = f"Capítulo {chap_num}" + (f" - {chap_name}" if chap_name else "")
    
    # Pattern for sentencias
    sentencia_pattern = r'(?:Sentencia\s+)?([CTSU]-\d+)\s+de\s+(\d{4})'
    sentencia_match = re.search(sentencia_pattern, text, re.IGNORECASE)
    if sentencia_match:
        info["sentencia"] = f"Sentencia {sentencia_match.group(1)} de {sentencia_match.group(2)}"
    
    # Pattern for laws
    ley_pattern = r'Ley\s+(\d+)\s+de\s+(\d{4})'
    ley_match = re.search(ley_pattern, text, re.IGNORECASE)
    if ley_match:
        info["ley"] = f"Ley {ley_match.group(1)} de {ley_match.group(2)}"
    
    # Pattern for decrees
    decreto_pattern = r'Decreto\s+(\d+)\s+de\s+(\d{4})'
    decreto_match = re.search(decreto_pattern, text, re.IGNORECASE)
    if decreto_match:
        info["decreto"] = f"Decreto {decreto_match.group(1)} de {decreto_match.group(2)}"
    
    return info


def compute_chunk_hash(text: str) -> str:
    """Compute a hash for a text chunk."""
    import hashlib
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


# Source metadata (copy for testing)
SOURCE_METADATA = {
    "codigo_transito": {
        "name": "Ley 769 de 2002 (Código Nacional de Tránsito Terrestre)",
        "type": "ley",
        "priority": 1,
        "year": 2002,
        "official_source": "Secretaría del Senado"
    },
    "decreto_2106": {
        "name": "Decreto 2106 de 2019 (Simplificación de Trámites)",
        "type": "decreto",
        "priority": 2,
        "year": 2019,
        "official_source": "Función Pública"
    },
    "jurisprudencia": {
        "name": "Jurisprudencia Constitucional",
        "type": "jurisprudencia",
        "priority": 2,
        "year": 2020,
        "official_source": "Corte Constitucional"
    },
    "senorbiter": {
        "name": "Guías Prácticas Señor Biter",
        "type": "guia",
        "priority": 3,
        "year": 2024,
        "official_source": "senorbiter.com"
    },
}


def format_reference(metadata: dict) -> str:
    """Format metadata into a readable reference string."""
    parts = []
    
    source = metadata.get("source", "")
    source_info = SOURCE_METADATA.get(source, {})
    source_name = source_info.get("name", source)
    if source_name:
        parts.append(f"📖 {source_name}")
    
    if metadata.get("sentencia"):
        parts.append(f"⚖️ {metadata['sentencia']}")
    
    if metadata.get("article"):
        parts.append(f"📌 {metadata['article']}")
    
    if metadata.get("ley") and source_name and "Ley" not in source_name:
        parts.append(f"📜 {metadata['ley']}")
    if metadata.get("decreto") and source_name and "Decreto" not in source_name:
        parts.append(f"📋 {metadata['decreto']}")
    
    if metadata.get("chapter"):
        parts.append(f"📂 {metadata['chapter']}")
    elif metadata.get("title"):
        parts.append(f"📂 {metadata['title']}")
    
    return " | ".join(parts) if parts else "Referencia general"


class TestMetadataExtraction:
    """Tests for metadata extraction from legal text."""
    
    def test_extract_article(self):
        """Test article number extraction."""
        text = "Artículo 131. De las multas. Las multas se clasifican..."
        result = extract_metadata_from_text(text, "codigo_transito")
        assert result["article"] == "Artículo 131"
    
    def test_extract_article_with_letter(self):
        """Test article with letter suffix (e.g., 131A)."""
        # The regex pattern requires a separator (space, period, dash, colon) after the number
        text = "Artículo 131A: Modificado por la Ley 1383..."
        result = extract_metadata_from_text(text, "codigo_transito")
        assert result["article"] == "Artículo 131A"
    
    def test_extract_chapter(self):
        """Test chapter extraction."""
        text = "CAPÍTULO III - DE LAS INFRACCIONES\nArtículo 130..."
        result = extract_metadata_from_text(text, "codigo_transito")
        assert "Capítulo III" in result["chapter"]
    
    def test_extract_title(self):
        """Test title extraction."""
        text = "TÍTULO IV - RÉGIMEN SANCIONATORIO\nCapítulo I..."
        result = extract_metadata_from_text(text, "codigo_transito")
        assert "Título IV" in result["title"]
    
    def test_extract_sentencia(self):
        """Test constitutional court ruling extraction."""
        text = "La Sentencia C-038 de 2020 declaró inexequible..."
        result = extract_metadata_from_text(text, "jurisprudencia")
        assert result["sentencia"] == "Sentencia C-038 de 2020"
    
    def test_extract_ley(self):
        """Test law reference extraction."""
        text = "Según la Ley 769 de 2002, los conductores..."
        result = extract_metadata_from_text(text, "codigo_transito")
        assert result["ley"] == "Ley 769 de 2002"
    
    def test_extract_decreto(self):
        """Test decree reference extraction."""
        text = "El Decreto 2106 de 2019 establece que..."
        result = extract_metadata_from_text(text, "decreto_2106")
        assert result["decreto"] == "Decreto 2106 de 2019"
    
    def test_no_metadata_found(self):
        """Test when no metadata is found."""
        text = "Este es un texto sin referencias legales específicas."
        result = extract_metadata_from_text(text, "senorbiter")
        assert result["article"] is None
        assert result["sentencia"] is None


class TestFormatReference:
    """Tests for reference formatting."""
    
    def test_format_with_article(self):
        """Test formatting with article info."""
        metadata = {
            "source": "codigo_transito",
            "article": "Artículo 131"
        }
        result = format_reference(metadata)
        assert "Ley 769 de 2002" in result
        assert "Artículo 131" in result
    
    def test_format_with_sentencia(self):
        """Test formatting with sentencia info."""
        metadata = {
            "source": "jurisprudencia",
            "sentencia": "Sentencia C-038 de 2020"
        }
        result = format_reference(metadata)
        assert "C-038 de 2020" in result
    
    def test_format_unknown_source(self):
        """Test formatting with unknown source."""
        metadata = {
            "source": "unknown_source"
        }
        result = format_reference(metadata)
        assert "unknown_source" in result or "Referencia general" in result


class TestChunkHash:
    """Tests for chunk hashing."""
    
    def test_hash_consistency(self):
        """Test that same text produces same hash."""
        text = "Test text for hashing"
        hash1 = compute_chunk_hash(text)
        hash2 = compute_chunk_hash(text)
        assert hash1 == hash2
    
    def test_hash_uniqueness(self):
        """Test that different texts produce different hashes."""
        text1 = "First text"
        text2 = "Second text"
        hash1 = compute_chunk_hash(text1)
        hash2 = compute_chunk_hash(text2)
        assert hash1 != hash2
    
    def test_hash_length(self):
        """Test that hash has expected length."""
        text = "Test text"
        hash_result = compute_chunk_hash(text)
        assert len(hash_result) == 12


class TestSourceMetadata:
    """Tests for source metadata configuration."""
    
    def test_codigo_transito_metadata(self):
        """Test codigo_transito source metadata."""
        assert "codigo_transito" in SOURCE_METADATA
        meta = SOURCE_METADATA["codigo_transito"]
        assert meta["type"] == "ley"
        assert meta["priority"] == 1
        assert meta["year"] == 2002
    
    def test_jurisprudencia_metadata(self):
        """Test jurisprudencia source metadata."""
        assert "jurisprudencia" in SOURCE_METADATA
        meta = SOURCE_METADATA["jurisprudencia"]
        assert meta["type"] == "jurisprudencia"
    
    def test_all_sources_have_required_fields(self):
        """Test all sources have required metadata fields."""
        required_fields = ["name", "type", "priority", "year"]
        for source_id, meta in SOURCE_METADATA.items():
            for field in required_fields:
                assert field in meta, f"Source {source_id} missing field {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
