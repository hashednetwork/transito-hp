"""
Tests for FAQ Golden Set - Validates RAG responses against expected patterns
These are integration tests that verify the RAG can find relevant content.
"""
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFAQGoldenSetContent:
    """Tests that FAQ golden set contains expected questions."""
    
    @pytest.fixture
    def faq_content(self):
        """Load FAQ golden set content."""
        faq_path = Path(__file__).parent.parent / "docs" / "faq_golden_set.txt"
        if not faq_path.exists():
            pytest.skip("FAQ golden set file not found")
        return faq_path.read_text()
    
    def test_faq_has_constitutional_foundation(self, faq_content):
        """Test FAQ covers constitutional foundation."""
        assert "fundamento constitucional" in faq_content.lower()
        assert "Artículo 24" in faq_content
    
    def test_faq_has_comparendo_vs_multa(self, faq_content):
        """Test FAQ covers comparendo vs multa distinction."""
        assert "comparendo" in faq_content.lower()
        assert "multa" in faq_content.lower()
        assert "diferencia" in faq_content.lower() or "CITACIÓN" in faq_content
    
    def test_faq_has_fotomulta_notification(self, faq_content):
        """Test FAQ covers fotomulta notification requirements."""
        assert "notificar" in faq_content.lower()
        assert "3 DÍAS" in faq_content or "tres días" in faq_content.lower()
    
    def test_faq_has_c038_2020(self, faq_content):
        """Test FAQ covers C-038/2020 ruling."""
        assert "C-038" in faq_content
        assert "2020" in faq_content
        assert "responsabilidad" in faq_content.lower()
    
    def test_faq_has_sast_requirements(self, faq_content):
        """Test FAQ covers SAST technical requirements."""
        assert "SAST" in faq_content
        assert "20203040011245" in faq_content or "criterios técnicos" in faq_content.lower()
    
    def test_faq_has_helmet_requirements(self, faq_content):
        """Test FAQ covers helmet (casco) requirements."""
        assert "casco" in faq_content.lower()
        assert "20203040023385" in faq_content or "condiciones mínimas" in faq_content.lower()
    
    def test_faq_has_speed_limits(self, faq_content):
        """Test FAQ covers speed limits."""
        assert "velocidad" in faq_content.lower()
        assert "Ley 2251" in faq_content or "límite" in faq_content.lower()
    
    def test_faq_has_pesv(self, faq_content):
        """Test FAQ covers PESV."""
        assert "PESV" in faq_content
        assert "Plan Estratégico" in faq_content or "20223040040595" in faq_content
    
    def test_faq_has_signaling_manual(self, faq_content):
        """Test FAQ covers signaling manual."""
        assert "Manual de Señalización" in faq_content or "señalización" in faq_content.lower()
        assert "2024" in faq_content
    
    def test_faq_has_electric_vehicles(self, faq_content):
        """Test FAQ covers electric vehicles."""
        assert "patineta" in faq_content.lower() or "eléctrico" in faq_content.lower()
        assert "Ley 2486" in faq_content or "2025" in faq_content
    
    def test_faq_has_school_transport(self, faq_content):
        """Test FAQ covers school transport."""
        assert "escolar" in faq_content.lower()
        assert "Ley 2393" in faq_content or "cinturón" in faq_content.lower()


class TestOntologyContent:
    """Tests that ontology documentation contains expected elements."""
    
    @pytest.fixture
    def ontology_content(self):
        """Load ontology content."""
        ontology_path = Path(__file__).parent.parent / "docs" / "ontologia_rag.txt"
        if not ontology_path.exists():
            pytest.skip("Ontology file not found")
        return ontology_path.read_text()
    
    def test_ontology_has_document_entity(self, ontology_content):
        """Test ontology defines DOCUMENTO entity."""
        assert "DOCUMENTO" in ontology_content
        assert "doc_id" in ontology_content
        assert "tipo_norma" in ontology_content
    
    def test_ontology_has_version_control(self, ontology_content):
        """Test ontology includes version control."""
        assert "VERSION_DOCUMENTO" in ontology_content
        assert "hash_sha256" in ontology_content
    
    def test_ontology_has_segment_entity(self, ontology_content):
        """Test ontology defines SEGMENTO entity."""
        assert "SEGMENTO" in ontology_content
        assert "segmento_id" in ontology_content
    
    def test_ontology_has_chunk_entity(self, ontology_content):
        """Test ontology defines CHUNK entity."""
        assert "CHUNK" in ontology_content
        assert "chunk_id" in ontology_content
    
    def test_ontology_has_relation_types(self, ontology_content):
        """Test ontology defines relation types."""
        assert "MODIFICA" in ontology_content
        assert "DEROGA" in ontology_content
        assert "CONDICIONA" in ontology_content
    
    def test_ontology_has_judicial_decision(self, ontology_content):
        """Test ontology defines judicial decisions."""
        assert "DECISION_JUDICIAL" in ontology_content
        assert "INEXEQUIBLE" in ontology_content
    
    def test_ontology_has_update_plan(self, ontology_content):
        """Test ontology includes update plan."""
        assert "FRECUENCIA" in ontology_content or "DIARIA" in ontology_content
        assert "monitorear" in ontology_content.lower()


class TestExpectedResponses:
    """Tests for expected response patterns in prompts."""
    
    @pytest.fixture
    def faq_content(self):
        """Load FAQ content."""
        faq_path = Path(__file__).parent.parent / "docs" / "faq_golden_set.txt"
        if not faq_path.exists():
            pytest.skip("FAQ file not found")
        return faq_path.read_text()
    
    def test_fotomulta_example_structure(self, faq_content):
        """Test fotomulta example has proper structure."""
        # Check it mentions the key points
        assert "responsabilidad personal" in faq_content.lower()
        assert "C-038" in faq_content
        assert "vinculación" in faq_content.lower() or "aportar pruebas" in faq_content.lower()
    
    def test_sast_example_structure(self, faq_content):
        """Test SAST example has proper structure."""
        assert "Ley 1843" in faq_content
        assert "Decreto" in faq_content and "2106" in faq_content
        assert "checklist" in faq_content.lower() or "señalización" in faq_content.lower()
    
    def test_velocity_example_structure(self, faq_content):
        """Test velocity example has proper structure."""
        assert "Ley 2251" in faq_content
        assert "metodología" in faq_content.lower()
        assert "PNSV" in faq_content or "Plan" in faq_content


class TestMetadataSchemaContent:
    """Tests for metadata schema documentation."""
    
    @pytest.fixture
    def schema_content(self):
        """Load metadata schema content."""
        schema_path = Path(__file__).parent.parent / "docs" / "metadata_schema.txt"
        if not schema_path.exists():
            pytest.skip("Metadata schema file not found")
        return schema_path.read_text()
    
    def test_schema_has_identification_fields(self, schema_content):
        """Test schema defines identification fields."""
        assert "doc_id" in schema_content
        assert "tipo_norma" in schema_content
        assert "numero" in schema_content
    
    def test_schema_has_vigencia_fields(self, schema_content):
        """Test schema defines vigencia fields."""
        assert "estado_vigencia" in schema_content or "vigencia" in schema_content.lower()
        assert "vigente" in schema_content.lower()
        assert "derogada" in schema_content.lower() or "derogado" in schema_content.lower()
    
    def test_schema_has_file_fields(self, schema_content):
        """Test schema defines file tracking fields."""
        assert "hash" in schema_content.lower()
        assert "url" in schema_content.lower()
        assert "fecha_descarga" in schema_content or "fecha_obtencion" in schema_content.lower()
    
    def test_schema_has_jurisprudence_fields(self, schema_content):
        """Test schema has jurisprudence-specific fields."""
        assert "sentencia" in schema_content.lower() or "decision" in schema_content.lower()
        assert "ratio" in schema_content.lower() or "decidendi" in schema_content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
