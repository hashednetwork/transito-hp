"""
Tests for the document generator
"""
import sys
from pathlib import Path
from io import BytesIO
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.document_generator import DerechoPeticionGenerator


class TestDerechoPeticionGenerator:
    """Tests for PDF document generation."""
    
    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return DerechoPeticionGenerator()
    
    @pytest.fixture
    def sample_data(self):
        """Sample data for document generation."""
        return {
            "template_type": "prescripcion",
            "nombre_completo": "Juan Carlos Pérez García",
            "cedula": "1.234.567.890",
            "direccion": "Calle 123 # 45-67, Bogotá",
            "telefono": "300 123 4567",
            "email": "juan.perez@email.com",
            "ciudad_autoridad": "Bogotá D.C.",
            "numero_comparendo": "ABC123456789",
            "fecha_infraccion": "15 de enero de 2022",
            "placa_vehiculo": "ABC-123",
            "hechos_adicionales": "La multa tiene más de 3 años y nunca fui notificado."
        }
    
    def test_available_templates(self, generator):
        """Test that all expected templates are available."""
        templates = generator.get_available_templates()
        
        expected = [
            "prescripcion",
            "fotomulta_notificacion",
            "fotomulta_identificacion",
            "fotomulta_señalizacion"
        ]
        
        for template in expected:
            assert template in templates
    
    def test_generate_prescripcion_pdf(self, generator, sample_data):
        """Test prescripción document generation."""
        sample_data["template_type"] = "prescripcion"
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        # Check PDF has content
        content = pdf_buffer.read()
        assert len(content) > 0
        # Check PDF magic bytes
        assert content[:4] == b'%PDF'
    
    def test_generate_fotomulta_notificacion_pdf(self, generator, sample_data):
        """Test fotomulta notification document generation."""
        sample_data["template_type"] = "fotomulta_notificacion"
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        content = pdf_buffer.read()
        assert len(content) > 0
        assert content[:4] == b'%PDF'
    
    def test_generate_fotomulta_identificacion_pdf(self, generator, sample_data):
        """Test fotomulta identification document generation."""
        sample_data["template_type"] = "fotomulta_identificacion"
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        content = pdf_buffer.read()
        assert len(content) > 0
    
    def test_generate_fotomulta_senalizacion_pdf(self, generator, sample_data):
        """Test fotomulta signalization document generation."""
        sample_data["template_type"] = "fotomulta_señalizacion"
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        content = pdf_buffer.read()
        assert len(content) > 0
    
    def test_invalid_template_raises_error(self, generator, sample_data):
        """Test that invalid template raises ValueError."""
        sample_data["template_type"] = "invalid_template"
        
        with pytest.raises(ValueError) as exc_info:
            generator.generate_document(**sample_data)
        
        assert "Unknown template type" in str(exc_info.value)
    
    def test_generate_without_hechos_adicionales(self, generator, sample_data):
        """Test document generation without additional facts."""
        sample_data["hechos_adicionales"] = ""
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        content = pdf_buffer.read()
        assert len(content) > 0
    
    def test_generate_with_special_characters(self, generator, sample_data):
        """Test document generation with special characters."""
        sample_data["nombre_completo"] = "José María Ñúñez Ávalos"
        sample_data["direccion"] = "Cra 5 # 23-45, Depto 301"
        sample_data["hechos_adicionales"] = "El día 15/01/2022 a las 10:30 a.m."
        
        pdf_buffer = generator.generate_document(**sample_data)
        
        assert isinstance(pdf_buffer, BytesIO)
        content = pdf_buffer.read()
        assert len(content) > 0
    
    def test_template_contains_legal_references(self, generator):
        """Test that templates contain proper legal references."""
        templates = generator.TEMPLATES
        
        # Prescripción should reference Art. 159 Ley 769
        assert "159" in templates["prescripcion"]["legal_basis"]
        assert "Ley 769" in templates["prescripcion"]["legal_basis"]
        
        # Notificación should reference Ley 1843
        assert "1843" in templates["fotomulta_notificacion"]["legal_basis"]
        assert "3 días" in templates["fotomulta_notificacion"]["legal_basis"].lower() or \
               "tres" in templates["fotomulta_notificacion"]["legal_basis"].lower()
        
        # Identificación should reference C-038 de 2020
        assert "C-038" in templates["fotomulta_identificacion"]["legal_basis"]
        
        # Señalización should reference 500 metros
        assert "500" in templates["fotomulta_señalizacion"]["legal_basis"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
