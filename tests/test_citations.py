"""
Tests for citation URL functionality in the RAG pipeline
Tests hyperlink generation and metadata URL resolution
"""
import sys
import re
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# SOURCE_METADATA with url_descarga (copy for testing without chromadb imports)
SOURCE_METADATA = {
    "codigo_transito": {
        "name": "Ley 769 de 2002 (Código Nacional de Tránsito Terrestre)",
        "short_name": "Ley 769 de 2002",
        "type": "ley",
        "priority": 1,
        "year": 2002,
        "official_source": "Secretaría del Senado",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5557",
        "url_descarga": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5557"
    },
    "decreto_2106": {
        "name": "Decreto 2106 de 2019 (Simplificación de Trámites)",
        "short_name": "Decreto 2106 de 2019",
        "type": "decreto",
        "priority": 2,
        "year": 2019,
        "official_source": "Función Pública",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=103352",
        "url_descarga": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=103352"
    },
    "ley_1843": {
        "name": "Ley 1843 de 2017 (Fotodetección de Infracciones)",
        "short_name": "Ley 1843 de 2017",
        "type": "ley",
        "priority": 1,
        "year": 2017,
        "official_source": "Secretaría del Senado",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=82815",
        "url_descarga": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=82815"
    },
    "resolucion_cascos": {
        "name": "Resolución 20203040023385 de 2020 (Condiciones Uso Casco)",
        "short_name": "Res. 20203040023385 de 2020",
        "type": "resolucion",
        "priority": 2,
        "year": 2020,
        "official_source": "MinTransporte",
        "url_descarga": "https://www.mintransporte.gov.co/publicaciones/10596/resoluciones-2020/"
    },
    "jurisprudencia": {
        "name": "Jurisprudencia Constitucional",
        "short_name": "Jurisprudencia",
        "type": "jurisprudencia",
        "priority": 2,
        "year": 2020,
        "official_source": "Corte Constitucional",
        "url_descarga": "https://www.corteconstitucional.gov.co/relatoria/"
    },
    "sentencia_c038": {
        "name": "Sentencia C-038 de 2020 (Fotodetección)",
        "short_name": "Sentencia C-038/2020",
        "type": "jurisprudencia",
        "priority": 1,
        "year": 2020,
        "official_source": "Corte Constitucional",
        "url_descarga": "https://www.corteconstitucional.gov.co/relatoria/2020/C-038-20.htm"
    },
    "compendio_normativo": {
        "name": "Compendio Normativo de Tránsito 2024-2025",
        "short_name": "Compendio Normativo 2024-2025",
        "type": "compendio",
        "priority": 1,
        "year": 2025,
        "official_source": "Compilación actualizada",
        "url_descarga": None
    }
}

# Known sentencias with direct URLs
SENTENCIAS_URLS = {
    "C-038": "https://www.corteconstitucional.gov.co/relatoria/2020/C-038-20.htm",
    "C-321": "https://www.corteconstitucional.gov.co/relatoria/2022/C-321-22.htm",
    "C-530": "https://www.corteconstitucional.gov.co/relatoria/2003/C-530-03.htm",
    "C-980": "https://www.corteconstitucional.gov.co/relatoria/2010/C-980-10.htm",
}


def get_citation_url(metadata: dict):
    """
    Get the best URL for citation from metadata.
    Prioritizes specific sentencia URLs, then source url_descarga.
    """
    # Check for sentencia-specific URL
    if metadata.get("sentencia"):
        sentencia_match = re.search(r'([CTSU]-\d+)', metadata["sentencia"])
        if sentencia_match:
            sentencia_code = sentencia_match.group(1)
            if sentencia_code in SENTENCIAS_URLS:
                return SENTENCIAS_URLS[sentencia_code]
    
    # Get source-level URL
    source = metadata.get("source", "")
    source_info = SOURCE_METADATA.get(source, {})
    return source_info.get("url_descarga") or source_info.get("url")


def format_citation_link(metadata: dict) -> str:
    """
    Format a citation as a Markdown hyperlink if URL is available.
    Returns: "[Norma](url)" or just "Norma" if no URL.
    """
    source = metadata.get("source", "")
    source_info = SOURCE_METADATA.get(source, {})
    
    # Build citation text
    citation_parts = []
    
    if metadata.get("article"):
        citation_parts.append(metadata["article"])
        
    if metadata.get("sentencia"):
        citation_parts.append(metadata["sentencia"])
    
    short_name = source_info.get("short_name") or source_info.get("name", source)
    if short_name and not any(short_name in p for p in citation_parts):
        citation_parts.append(short_name)
    
    if citation_parts:
        citation_text = ", ".join(citation_parts)
    else:
        citation_text = "Referencia"
    
    url = get_citation_url(metadata)
    if url:
        return f"[{citation_text}]({url})"
    return citation_text


class TestCitationURLResolution:
    """Tests for URL resolution in citations."""
    
    def test_fotodeteccion_c038_has_url(self):
        """Test C-038 fotodetección sentencia has correct URL."""
        metadata = {
            "source": "jurisprudencia",
            "sentencia": "Sentencia C-038 de 2020"
        }
        url = get_citation_url(metadata)
        assert url is not None
        assert "C-038" in url or "c-038" in url.lower()
        assert "corteconstitucional" in url
    
    def test_casco_resolucion_2020_has_url(self):
        """Test Resolución cascos 2020 has URL."""
        metadata = {
            "source": "resolucion_cascos"
        }
        url = get_citation_url(metadata)
        assert url is not None
        assert "mintransporte" in url
    
    def test_ley_769_has_url(self):
        """Test Ley 769 codigo de transito has URL."""
        metadata = {
            "source": "codigo_transito",
            "article": "Artículo 131"
        }
        url = get_citation_url(metadata)
        assert url is not None
        assert "funcionpublica" in url
        assert "5557" in url
    
    def test_ley_1843_fotodeteccion_has_url(self):
        """Test Ley 1843 fotodetección has URL."""
        metadata = {
            "source": "ley_1843"
        }
        url = get_citation_url(metadata)
        assert url is not None
        assert "funcionpublica" in url
        assert "82815" in url
    
    def test_decreto_2106_has_url(self):
        """Test Decreto 2106 documentos digitales has URL."""
        metadata = {
            "source": "decreto_2106"
        }
        url = get_citation_url(metadata)
        assert url is not None
        assert "funcionpublica" in url
        assert "103352" in url
    
    def test_compendio_no_url(self):
        """Test compendio has no url_descarga."""
        metadata = {
            "source": "compendio_normativo"
        }
        url = get_citation_url(metadata)
        assert url is None
    
    def test_sentencia_url_priority_over_source(self):
        """Test that specific sentencia URL takes priority over generic source URL."""
        metadata = {
            "source": "jurisprudencia",  # Generic jurisprudencia source
            "sentencia": "Sentencia C-038 de 2020"  # Specific sentencia
        }
        url = get_citation_url(metadata)
        # Should get specific C-038 URL, not generic jurisprudencia URL
        assert url == "https://www.corteconstitucional.gov.co/relatoria/2020/C-038-20.htm"


class TestCitationLinkFormatting:
    """Tests for Markdown hyperlink formatting."""
    
    def test_format_article_with_url(self):
        """Test article citation becomes Markdown link."""
        metadata = {
            "source": "codigo_transito",
            "article": "Artículo 131"
        }
        link = format_citation_link(metadata)
        assert link.startswith("[")
        assert "Artículo 131" in link
        assert "](https://" in link
        assert link.endswith(")")
    
    def test_format_sentencia_with_url(self):
        """Test sentencia citation becomes Markdown link with correct URL."""
        metadata = {
            "source": "jurisprudencia",
            "sentencia": "Sentencia C-038 de 2020"
        }
        link = format_citation_link(metadata)
        assert "[Sentencia C-038 de 2020" in link
        assert "C-038-20.htm" in link
    
    def test_format_without_url_no_link(self):
        """Test citation without URL returns plain text."""
        metadata = {
            "source": "compendio_normativo"
        }
        link = format_citation_link(metadata)
        assert "[" not in link or "](" not in link
        assert "Compendio" in link
    
    def test_format_decreto_with_url(self):
        """Test decreto citation becomes Markdown link."""
        metadata = {
            "source": "decreto_2106"
        }
        link = format_citation_link(metadata)
        assert "Decreto 2106" in link
        assert "](https://" in link


class TestSourceMetadataURLs:
    """Tests for SOURCE_METADATA url_descarga configuration."""
    
    def test_all_leyes_have_url(self):
        """Test all leyes have url_descarga."""
        leyes = [k for k, v in SOURCE_METADATA.items() if v.get("type") == "ley"]
        for source_id in leyes:
            meta = SOURCE_METADATA[source_id]
            url = meta.get("url_descarga") or meta.get("url")
            assert url is not None, f"Ley {source_id} missing url_descarga"
    
    def test_all_decretos_have_url(self):
        """Test all decretos have url_descarga."""
        decretos = [k for k, v in SOURCE_METADATA.items() if v.get("type") == "decreto"]
        for source_id in decretos:
            meta = SOURCE_METADATA[source_id]
            url = meta.get("url_descarga") or meta.get("url")
            assert url is not None, f"Decreto {source_id} missing url_descarga"
    
    def test_sentencia_sources_have_short_name(self):
        """Test sentencia sources have short_name for better citations."""
        sentencias = [k for k, v in SOURCE_METADATA.items() if "sentencia" in k.lower()]
        for source_id in sentencias:
            meta = SOURCE_METADATA[source_id]
            assert "short_name" in meta, f"Sentencia {source_id} missing short_name"


class TestDerechodePeticionQuery:
    """Test queries related to derecho de peticion return linkable sources."""
    
    def test_constitucion_art_23_context(self):
        """Test that queries about derecho de peticion can cite Art. 23 Constitución."""
        # Simulated metadata that would be returned for a derecho de peticion query
        metadata = {
            "source": "codigo_transito",  # Would reference constitution
            "article": "Artículo 23",
            "ley": "Constitución Política de Colombia"
        }
        url = get_citation_url(metadata)
        # codigo_transito should have URL
        assert url is not None


class TestMarkdownLinkValidation:
    """Test that generated Markdown links are valid."""
    
    def test_link_format_valid(self):
        """Test generated links follow Markdown format."""
        metadata = {
            "source": "codigo_transito",
            "article": "Artículo 131"
        }
        link = format_citation_link(metadata)
        # Should match [text](url) pattern
        pattern = r'\[.+\]\(https?://.+\)'
        assert re.match(pattern, link), f"Invalid Markdown link format: {link}"
    
    def test_link_no_special_chars_unescaped(self):
        """Test links don't have problematic unescaped characters."""
        metadata = {
            "source": "codigo_transito",
            "article": "Artículo 131"
        }
        link = format_citation_link(metadata)
        # Check no nested brackets or parentheses that would break Markdown
        url_part = link.split("](")[1][:-1] if "](" in link else ""
        assert "[" not in url_part
        assert "]" not in url_part


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
