#!/usr/bin/env python3
"""
TransitoColBot - Colombian Transit Law Telegram Bot
Enhanced version with multi-document RAG
"""
# Fix SQLite version for ChromaDB (must be before any sqlite imports)
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transito-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.rag import initialize_rag
from src.bot import create_bot


def validate_environment() -> bool:
    """Validate required environment variables."""
    required_vars = ["TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        print("\n❌ Error: Missing environment variables!")
        print("Please ensure .env file contains:")
        for var in required_vars:
            status = "✅" if os.getenv(var) else "❌"
            print(f"  {status} {var}")
        return False
    
    return True


def main():
    """Main entry point."""
    print("=" * 60)
    print("🚗 TransitoColBot - Colombian Transit Law Assistant")
    print("   Enhanced RAG with multi-document support")
    print("=" * 60)
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Paths
    project_dir = Path(__file__).parent
    chroma_dir = project_dir / "chroma_db"
    
    # Check for required documents
    required_docs = [
        project_dir / "codigo_transito.txt",
    ]
    optional_docs = [
        project_dir / "decreto_2106_2019.txt",
        project_dir / "senorbiter_guias.txt",
        project_dir / "docs" / "compendio_normativo.txt",
    ]
    
    print("\n📂 Checking documents...")
    for doc in required_docs:
        if not doc.exists():
            logger.error(f"Required document not found: {doc}")
            print(f"  ❌ {doc.name} (REQUIRED)")
            sys.exit(1)
        print(f"  ✅ {doc.name}")
    
    for doc in optional_docs:
        if doc.exists():
            print(f"  ✅ {doc.name}")
        else:
            print(f"  ⚪ {doc.name} (optional, not found)")
    
    # Initialize RAG pipeline
    print("\n📚 Initializing enhanced RAG pipeline...")
    print("   This may take a moment for first-time indexing...")
    
    try:
        # Check if we need to force reindex (if collection name changed)
        force_reindex = os.getenv("FORCE_REINDEX", "").lower() == "true"
        
        rag = initialize_rag(
            base_path=str(project_dir),
            persist_directory=str(chroma_dir),
            force_reindex=force_reindex
        )
        
        stats = rag.get_stats()
        print(f"\n✅ RAG pipeline ready!")
        print(f"   Total chunks indexed: {stats['total_chunks']}")
        print("   Sources:")
        for source, count in stats['by_source'].items():
            if count > 0:
                print(f"     • {source}: {count} chunks")
        
    except Exception as e:
        logger.error(f"Failed to initialize RAG pipeline: {e}")
        print(f"\n❌ Failed to initialize RAG: {e}")
        sys.exit(1)
    
    # Show LLM configuration
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    print(f"\n🤖 LLM Model: {llm_model}")
    
    # Create and run bot
    print("\n🚀 Starting Telegram bot...")
    print("   Press Ctrl+C to stop.\n")
    
    try:
        bot = create_bot(rag)
        bot.run()
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user.")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        print(f"\n❌ Bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
