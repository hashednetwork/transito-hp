#!/usr/bin/env python3
"""
Transito HP - Colombian Transit Code Telegram Bot
Main entry point
"""
# Fix SQLite version for ChromaDB
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.rag import initialize_rag
from src.bot import create_bot


def main():
    """Main entry point."""
    # Validate environment variables
    required_vars = ["TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Please ensure .env file contains TELEGRAM_BOT_TOKEN and OPENAI_API_KEY")
        sys.exit(1)
    
    # Paths
    project_dir = Path(__file__).parent
    document_path = project_dir / "codigo_transito.txt"
    chroma_dir = project_dir / "chroma_db"
    
    # Check if document exists
    if not document_path.exists():
        print(f"Error: Document not found at {document_path}")
        sys.exit(1)
    
    print("=" * 50)
    print("🚗 Transito HP - Colombian Transit Code Bot")
    print("=" * 50)
    
    # Initialize RAG pipeline
    print("\n📚 Initializing RAG pipeline...")
    rag = initialize_rag(
        document_path=str(document_path),
        persist_directory=str(chroma_dir)
    )
    print(f"✅ RAG pipeline ready with {rag.collection.count()} indexed chunks")
    
    # Create and run bot
    print("\n🤖 Starting Telegram bot...")
    bot = create_bot(rag)
    bot.run()


if __name__ == "__main__":
    main()
