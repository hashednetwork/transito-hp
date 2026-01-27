"""
Telegram Bot for Colombian Transit Code Q&A
"""
import os
import logging
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

from .rag import RAGPipeline

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# System prompt for the LLM
SYSTEM_PROMPT = """Eres un asistente legal especializado en normativa de tránsito de Colombia, incluyendo:
- Ley 769 de 2002 (Código Nacional de Tránsito Terrestre) y sus modificaciones
- Decreto 2106 de 2019 (Simplificación de trámites - incluye artículos sobre transporte, fotomultas, licencias y multas)

Tu rol es:
- Responder preguntas basándote ÚNICAMENTE en los artículos proporcionados en el contexto
- Citar los artículos y la ley/decreto específicos cuando sea posible (ejemplo: "Según el Artículo 131 de la Ley 769..." o "Según el Artículo 111 del Decreto 2106...")
- Responder siempre en español
- Si la información no está en el contexto proporcionado, indicar que no tienes esa información específica
- Ser preciso y conciso en tus respuestas
- No inventar información que no esté en los artículos proporcionados
- Informar a los conductores sobre sus derechos, especialmente cuando las autoridades no pueden exigir documentos físicos si pueden consultarlos digitalmente (RUNT)"""


class TransitoBot:
    def __init__(self, rag_pipeline: RAGPipeline, telegram_token: str):
        """Initialize the Telegram bot with RAG pipeline."""
        self.rag = rag_pipeline
        self.telegram_token = telegram_token
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.application: Optional[Application] = None
        
    def _generate_response(self, query: str, context: str) -> str:
        """Generate a response using GPT-4 with the retrieved context."""
        user_message = f"""Contexto del Código de Tránsito:

{context}

---

Pregunta del usuario: {query}

Por favor responde basándote únicamente en el contexto proporcionado."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using gpt-4o-mini for cost efficiency, can upgrade to gpt-4o
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Lo siento, hubo un error procesando tu pregunta. Por favor intenta de nuevo."
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        welcome_message = """🚗 ¡Bienvenido al Bot del Código de Tránsito de Colombia!

Soy un asistente especializado en normativa de tránsito colombiana:
• Ley 769 de 2002 (Código Nacional de Tránsito)
• Decreto 2106 de 2019 (Simplificación de trámites)

📚 **¿Cómo puedo ayudarte?**
Simplemente envíame tu pregunta sobre:
• Normas de tránsito y señales
• Límites de velocidad
• Multas, infracciones y descuentos por pronto pago
• Licencias de conducción y requisitos
• Derechos de conductores (documentos digitales vs físicos)
• Revisión técnico-mecánica
• Sistemas de fotomultas
• Y cualquier otro tema del código de tránsito

✍️ **Ejemplos de preguntas:**
• "¿Cuál es la multa por no usar el cinturón de seguridad?"
• "¿Me pueden exigir el certificado físico de la revisión técnico-mecánica?"
• "¿Cómo puedo obtener descuento en una multa?"

¡Hazme tu pregunta!"""
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_message = """📖 **Ayuda - Bot del Código de Tránsito**

**Comandos disponibles:**
/start - Mensaje de bienvenida
/help - Esta ayuda

**¿Cómo usar el bot?**
Simplemente escribe tu pregunta sobre el código de tránsito colombiano y te responderé basándome en los artículos relevantes.

**Tips para mejores respuestas:**
• Sé específico en tu pregunta
• Menciona el tema concreto (multas, velocidad, licencias, etc.)
• Puedes preguntar por artículos específicos

**Ejemplos:**
• "¿Qué dice el artículo 131 sobre infracciones?"
• "¿Cuáles son los requisitos para obtener licencia de conducción?"
• "¿Qué sanciones hay por conducir embriagado?"
"""
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages."""
        user_query = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Query from user {user_id}: {user_query}")
        
        # Send typing indicator
        await update.message.chat.send_action("typing")
        
        try:
            # Retrieve relevant context from RAG
            rag_context = self.rag.get_context_for_query(user_query, n_results=5)
            
            # Generate response with GPT-4
            response = self._generate_response(user_query, rag_context)
            
            # Send response
            await update.message.reply_text(response)
            logger.info(f"Sent response to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error procesando tu pregunta. Por favor intenta de nuevo más tarde."
            )
    
    def run(self) -> None:
        """Run the bot."""
        logger.info("Starting Transito HP Bot...")
        
        # Create application
        self.application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start polling
        logger.info("Bot is running. Press Ctrl+C to stop.")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def create_bot(rag_pipeline: RAGPipeline) -> TransitoBot:
    """Create and return a bot instance."""
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    return TransitoBot(rag_pipeline, telegram_token)
