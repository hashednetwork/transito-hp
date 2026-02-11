# TransitoColBot 🚗⚖️

AI-powered Telegram bot for Colombian transit law assistance. Helps drivers understand their rights, contest fines, and generate legal documents.

## Features

### 🔍 Intelligent Q&A
- Natural language queries in Spanish
- Multi-document RAG (Retrieval-Augmented Generation)
- Citations with specific articles and laws
- Jurisprudence references

### 🎤 Voice Support
- Voice message input (Whisper transcription)
- Audio response output (TTS)
- `/voz` command for text+audio responses

### 📄 Document Generation
- **Derecho de Petición** PDF generation
- Templates for:
  - Prescripción (multas > 3 años)
  - Fotomulta sin notificación oportuna
  - Fotomulta sin identificación del conductor
  - Fotomulta sin señalización adecuada

### 📊 Analytics & Rate Limiting
- Usage tracking per user
- Daily query limits (10/day free tier)
- Admin statistics dashboard

## Knowledge Base

### Normative Hierarchy (Highest to Lowest)

#### 1. Constitution (Maximum Force)
- **Constitución Política 1991** - Art. 24 (circulation), Art. 23 (petition), Art. 29 (due process)

#### 2. Laws & Codes (High Force)
- **Ley 769 de 2002** - Código Nacional de Tránsito Terrestre (main axis)
- **Ley 1383 de 2010** - Reforma al Código de Tránsito
- **Ley 1696 de 2013** - Sanciones por embriaguez
- **Ley 1843 de 2017** - Fotodetección de infracciones
- **Ley 2393 de 2024** - Cinturón de seguridad escolar
- **Ley 2435 de 2024** - Ajustes sancionatorios
- **Ley 2486 de 2025** - Vehículos eléctricos de movilidad personal

#### 3. Decrees (Regulatory)
- **Decreto 1079 de 2015** - Decreto Único Reglamentario del sector transporte
- **Decreto 2106 de 2019** - Simplificación de trámites (documentos digitales)

#### 4. Resolutions (Technical/Administrative)
- **Resolución 20223040045295/2022** - Resolución Única Compilatoria MinTransporte
- **Resolución 20243040045005/2024** - Manual de Señalización Vial 2024 (Anexo 76)
- **Resolución 20203040011245/2020** - Criterios técnicos SAST/fotodetección
- **Resolución 20233040025995/2023** - Metodología de velocidad límite
- **Resolución 20233040025895/2023** - Planes de gestión de velocidad
- **Resolución 20223040040595/2022** - Metodología PESV
- **Resolución 20203040023385/2020** - Condiciones de uso del casco

#### 5. Jurisprudence (Interpretive/Conditioning)
- **C-530 de 2003** - Debido proceso en comparendos
- **C-980 de 2010** - Notificación válida
- **C-038 de 2020** - Responsabilidad personal en fotomultas
- **Concepto Rad. 2433/2020** - Consejo de Estado sobre fotomultas/privados

#### 6. Circulars (Operational Guidelines)
- **Circular Conjunta 023/2025** - Plan 365 (pedagogía y control)
- **Circular Externa 20254000000867** - SAST y control de señalización

#### 7. Guides & Compilations
- Compendio Normativo 2024-2025 (25+ documents referenced)
- Inventario de Documentos Oficiales
- Guías Señor Biter (defensa del conductor)

## Tech Stack

- **Python 3.9+**
- **Telegram Bot API** (python-telegram-bot v20+)
- **OpenAI API**
  - GPT-4o-mini for responses
  - text-embedding-3-small for RAG
  - Whisper for transcription
  - TTS for voice output
- **ChromaDB** - Vector store with persistence
- **ReportLab** - PDF generation
- **SQLite** - Analytics storage

## Installation

### Prerequisites
- Python 3.9+
- OpenAI API key
- Telegram Bot Token

### Setup

```bash
# Clone repository
git clone https://github.com/hashednetwork/TransitoCol.git
cd TransitoCol

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables

Create a `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key

# Optional
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=1200
FORCE_REINDEX=false
```

### Running

```bash
# Run the bot
python main.py

# Run tests
pytest tests/ -v
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/help` | Detailed help and usage tips |
| `/voz [pregunta]` | Get text + audio response |
| `/documento` | Generate Derecho de Petición PDF |
| `/fuentes` | View indexed legal sources |
| `/stats` | Usage statistics (admin only) |

## Usage Examples

### Text Queries
```
"¿Me pueden exigir documentos físicos en un retén?"
"¿Cómo tumbar una fotomulta?"
"¿Las multas de tránsito prescriben?"
"¿Qué dice la Sentencia C-038 de 2020?"
```

### Voice Command
```
/voz ¿Cuánto tiempo tiene la autoridad para notificarme una fotomulta?
```

### Document Generation
Use `/documento` and follow the interactive prompts to generate a customized Derecho de Petición.

## Project Structure

```
transitocol/
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── .env                    # API keys (not tracked)
├── chroma_db/              # Vector database (persistent)
├── docs/
│   ├── compendio_normativo.txt
│   └── inventario_documentos.txt
├── src/
│   ├── __init__.py
│   ├── rag.py              # Enhanced RAG pipeline
│   ├── bot.py              # Telegram bot handlers
│   ├── document_generator.py  # PDF generation
│   └── analytics.py        # Usage tracking
├── tests/
│   ├── test_rag.py
│   ├── test_document_generator.py
│   └── test_analytics.py
├── codigo_transito.txt     # Source: Ley 769 de 2002
├── decreto_2106_2019.txt   # Source: Decreto 2106
└── senorbiter_guias.txt    # Source: Practical guides
```

## RAG Architecture

1. **Document Processing**
   - Smart chunking based on document type (legal articles, guides, jurisprudence)
   - Metadata extraction (article numbers, law references, sentencias)
   - Hash-based deduplication

2. **Embedding & Storage**
   - OpenAI text-embedding-3-small
   - ChromaDB with cosine similarity
   - Persistent storage with incremental updates

3. **Retrieval**
   - Query embedding with relevance scoring
   - Source priority boosting (laws > decrees > guides)
   - Reference formatting for citations

4. **Generation**
   - Context-aware prompting
   - Specialized system prompts for text vs voice
   - Legal citation requirements

## Key Driver Rights (Emphasized)

1. **Digital Documents**: Authorities cannot require physical documents if verifiable in RUNT (Decree 2106/2019)
2. **Photo-radar Requirements**:
   - Notification within 3 business days
   - Signage 500m before camera
   - Driver must be identified (not automatic owner liability - C-038/2020)
   - Camera must be authorized by ANSV
3. **Prescription**: Fines prescribe after 3 years
4. **Discounts**: 50% within 5 days, 25% within 20 days

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

MIT

## Disclaimer

This bot provides informational assistance only. It is not legal advice. Always consult with a qualified legal professional for specific legal matters. The information is based on Colombian transit law as of 2025.

---

**Built with ❤️ for Colombian drivers**
