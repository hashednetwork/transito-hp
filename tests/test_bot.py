"""
Tests for the bot module
"""
import sys
import re
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDerechoPeticionTrigger:
    """Tests for derecho de petición trigger regex."""
    
    @pytest.fixture
    def trigger_pattern(self):
        """The regex pattern used for derecho de petición trigger."""
        return re.compile(r'(?i)(derecho.*peticion|crear.*(derecho.*peticion|documento)|peticion.*derecho)')
    
    def test_matches_derecho_de_peticion(self, trigger_pattern):
        """Test matching 'derecho de petición'."""
        assert trigger_pattern.search("derecho de peticion")
        assert trigger_pattern.search("Derecho de Peticion")
        assert trigger_pattern.search("DERECHO DE PETICION")
    
    def test_matches_without_accent(self, trigger_pattern):
        """Test matching without accent marks (as typed by many users)."""
        assert trigger_pattern.search("derecho de peticion")
    
    def test_matches_crear_derecho(self, trigger_pattern):
        """Test matching 'crear derecho de petición'."""
        assert trigger_pattern.search("quiero crear un derecho de peticion")
        assert trigger_pattern.search("crear derecho de peticion")
    
    def test_matches_crear_documento(self, trigger_pattern):
        """Test matching 'crear documento'."""
        assert trigger_pattern.search("crear documento")
        assert trigger_pattern.search("quiero crear un documento")
    
    def test_matches_peticion_derecho(self, trigger_pattern):
        """Test matching reversed 'petición derecho'."""
        assert trigger_pattern.search("peticion de derecho")
    
    def test_no_match_unrelated(self, trigger_pattern):
        """Test no match for unrelated queries."""
        assert not trigger_pattern.search("multa de tránsito")
        assert not trigger_pattern.search("fotomulta")
        assert not trigger_pattern.search("velocidad máxima")
    
    def test_matches_question_format(self, trigger_pattern):
        """Test matching question formats."""
        assert trigger_pattern.search("Como hago un derecho de peticion")
        assert trigger_pattern.search("como crear un derecho de peticion")


class TestSystemPromptContent:
    """Tests for system prompt content."""
    
    @pytest.fixture
    def system_prompt(self):
        """Load the system prompt from bot.py."""
        # Read the file and extract SYSTEM_PROMPT
        bot_path = Path(__file__).parent.parent / "src" / "bot.py"
        content = bot_path.read_text()
        
        # Find SYSTEM_PROMPT definition
        start = content.find('SYSTEM_PROMPT = """')
        if start == -1:
            pytest.skip("Could not find SYSTEM_PROMPT in bot.py")
        
        start += len('SYSTEM_PROMPT = """')
        end = content.find('"""', start)
        return content[start:end]
    
    def test_prompt_mentions_constitution(self, system_prompt):
        """Test that prompt mentions Constitution."""
        assert "Constitución" in system_prompt or "CONSTITUCIÓN" in system_prompt
        assert "Art. 24" in system_prompt or "art. 24" in system_prompt
    
    def test_prompt_mentions_codigo_transito(self, system_prompt):
        """Test that prompt mentions Código de Tránsito."""
        assert "Ley 769" in system_prompt
        assert "2002" in system_prompt
    
    def test_prompt_mentions_fotodeteccion(self, system_prompt):
        """Test that prompt mentions fotodetección law."""
        assert "1843" in system_prompt
        assert "fotodetección" in system_prompt.lower() or "fotomultas" in system_prompt.lower()
    
    def test_prompt_mentions_c038(self, system_prompt):
        """Test that prompt mentions C-038 de 2020."""
        assert "C-038" in system_prompt
        assert "2020" in system_prompt
    
    def test_prompt_mentions_decreto_2106(self, system_prompt):
        """Test that prompt mentions Decreto 2106."""
        assert "2106" in system_prompt
        assert "2019" in system_prompt
    
    def test_prompt_mentions_sast(self, system_prompt):
        """Test that prompt mentions SAST criteria."""
        assert "SAST" in system_prompt or "fotodetección" in system_prompt.lower()
    
    def test_prompt_has_normative_hierarchy(self, system_prompt):
        """Test that prompt includes normative hierarchy."""
        assert "jerarquía" in system_prompt.lower() or "CONSTITUCIÓN" in system_prompt
        assert "Leyes" in system_prompt or "LEYES" in system_prompt
        assert "Decretos" in system_prompt or "DECRETOS" in system_prompt
        assert "Resoluciones" in system_prompt or "RESOLUCIONES" in system_prompt


class TestRateLimitConfig:
    """Tests for rate limit configuration."""
    
    def test_daily_limit_constant_exists(self):
        """Test that DAILY_QUERY_LIMIT is defined."""
        bot_path = Path(__file__).parent.parent / "src" / "bot.py"
        content = bot_path.read_text()
        assert "DAILY_QUERY_LIMIT" in content
    
    def test_admin_ids_defined(self):
        """Test that ADMIN_IDS is defined."""
        bot_path = Path(__file__).parent.parent / "src" / "bot.py"
        content = bot_path.read_text()
        assert "ADMIN_IDS" in content


class TestBotCommands:
    """Tests for bot command definitions."""
    
    @pytest.fixture
    def bot_content(self):
        """Load bot.py content."""
        bot_path = Path(__file__).parent.parent / "src" / "bot.py"
        return bot_path.read_text()
    
    def test_start_command_exists(self, bot_content):
        """Test /start command is defined."""
        assert "async def start_command" in bot_content
        assert 'CommandHandler("start"' in bot_content
    
    def test_help_command_exists(self, bot_content):
        """Test /help command is defined."""
        assert "async def help_command" in bot_content
        assert 'CommandHandler("help"' in bot_content
    
    def test_fuentes_command_exists(self, bot_content):
        """Test /fuentes command is defined."""
        assert "async def fuentes_command" in bot_content
        assert 'CommandHandler("fuentes"' in bot_content
    
    def test_voz_command_exists(self, bot_content):
        """Test /voz command is defined."""
        assert "async def voz_command" in bot_content
        assert 'CommandHandler("voz"' in bot_content
    
    def test_documento_command_exists(self, bot_content):
        """Test /documento command is defined."""
        assert "async def documento_command" in bot_content
        assert 'CommandHandler("documento"' in bot_content
    
    def test_stats_command_exists(self, bot_content):
        """Test /stats command is defined."""
        assert "async def stats_command" in bot_content
        assert 'CommandHandler("stats"' in bot_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
