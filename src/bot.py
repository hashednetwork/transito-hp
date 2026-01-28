"""
Telegram Bot for Colombian Transit Code Q&A
"""
import os
import logging
import tempfile
from typing import Optional
from pathlib import Path

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
- Decreto 2106 de 2019 (Simplificación de trámites - transporte, fotomultas, licencias y multas)
- Guías prácticas de defensa del Señor Biter (educador en derechos de conductores)

Tu rol es:
- Responder preguntas basándote ÚNICAMENTE en la información proporcionada en el contexto
- Citar los artículos y la ley/decreto específicos cuando sea posible (ejemplo: "Según el Artículo 131 de la Ley 769..." o "Según el Artículo 111 del Decreto 2106...")
- Dar consejos prácticos sobre cómo defender los derechos del conductor
- Responder siempre en español
- Si la información no está en el contexto proporcionado, indicar que no tienes esa información específica
- Ser preciso y conciso en tus respuestas
- No inventar información que no esté en los artículos proporcionados
- Informar a los conductores sobre sus derechos, especialmente:
  * Las autoridades NO pueden exigir documentos físicos si pueden consultarlos digitalmente (RUNT)
  * Fotomultas deben cumplir requisitos específicos (notificación en 3 días, señalización 500m antes, cámaras autorizadas)
  * Las multas prescriben en 3 años
  * Hay descuentos del 50%-75% por pronto pago"""


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
    
    def _transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio file using OpenAI Whisper API."""
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="es"  # Spanish
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise
    
    def _text_to_speech(self, text: str, output_path: str) -> bool:
        """Convert text to speech using OpenAI TTS API."""
        try:
            # Limit text length for TTS (max ~4096 chars works well)
            if len(text) > 4000:
                text = text[:4000] + "... Para más detalles, lee el mensaje de texto."
            
            response = self.openai_client.audio.speech.create(
                model="tts-1",  # or "tts-1-hd" for higher quality
                voice="nova",   # Options: alloy, echo, fable, onyx, nova, shimmer
                input=text,
                response_format="opus"  # Good for Telegram voice messages
            )
            
            # Save to file
            response.stream_to_file(output_path)
            return True
        except Exception as e:
            logger.error(f"Error generating TTS: {e}")
            return False
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming voice messages."""
        user_id = update.effective_user.id
        logger.info(f"Voice message from user {user_id}")
        
        # Send typing indicator
        await update.message.chat.send_action("typing")
        
        try:
            # Get voice file from Telegram
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            
            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
                tmp_path = tmp_file.name
                await file.download_to_drive(tmp_path)
            
            try:
                # Transcribe audio
                logger.info(f"Transcribing voice message from user {user_id}")
                transcribed_text = self._transcribe_audio(tmp_path)
                logger.info(f"Transcribed: {transcribed_text[:100]}...")
                
                # Show user what we understood
                await update.message.reply_text(f"🎤 *Entendí:* _{transcribed_text}_\n\n⏳ Buscando respuesta...", parse_mode='Markdown')
                
                # Process through RAG pipeline (same as text)
                rag_context = self.rag.get_context_for_query(transcribed_text, n_results=5)
                response = self._generate_response(transcribed_text, rag_context)
                
                # Send text response first
                await update.message.reply_text(response)
                
                # Also send voice response since user sent voice
                voice_path = tmp_path.replace(".ogg", "_response.opus")
                if self._text_to_speech(response, voice_path):
                    try:
                        await update.message.reply_voice(voice=open(voice_path, "rb"))
                        logger.info(f"Sent voice response to user {user_id}")
                    finally:
                        Path(voice_path).unlink(missing_ok=True)
                
                logger.info(f"Sent response to voice query from user {user_id}")
                
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)
                
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error procesando tu mensaje de voz. Por favor intenta de nuevo o escribe tu pregunta."
            )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        welcome_message = """🚗 ¡Bienvenido al Bot del Código de Tránsito de Colombia!

Soy un asistente especializado en normativa de tránsito colombiana:
• Ley 769 de 2002 (Código Nacional de Tránsito)
• Decreto 2106 de 2019 (Simplificación de trámites)

📚 **¿Cómo puedo ayudarte?**
Escríbeme o **envíame un audio** 🎤 explicando tu situación:
• Normas de tránsito y señales
• Multas, infracciones y descuentos
• Licencias de conducción
• Derechos de conductores (documentos digitales vs físicos)
• Cómo defenderte de fotomultas
• Revisión técnico-mecánica
• Y cualquier otro tema del código de tránsito

✍️ **Ejemplos:**
• "¿Cuál es la multa por no usar cinturón?"
• "¿Me pueden exigir documentos físicos en un retén?"
• "¿Cómo tumbo una fotomulta?"

🎤 **También puedes enviar audio** explicando tu caso y te ayudo.

¡Hazme tu pregunta!"""
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_message = """📖 **Ayuda - Bot del Código de Tránsito**

**Comandos disponibles:**
/start - Mensaje de bienvenida
/help - Esta ayuda
/voz [pregunta] - Respuesta en texto Y audio 🔊

**¿Cómo usar el bot?**
• Escribe tu pregunta → respuesta en texto
• Envía audio 🎤 → respuesta en texto + audio
• Usa /voz [pregunta] → respuesta en texto + audio

**Tips para mejores respuestas:**
• Sé específico en tu pregunta
• Menciona el tema concreto (multas, velocidad, licencias, etc.)

**Ejemplos:**
• "¿Cuál es la multa por no usar cinturón?"
• /voz ¿Me pueden quitar la licencia por multas?
• 🎤 [audio explicando tu caso]
"""
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def voz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /voz command - respond with text AND voice."""
        user_id = update.effective_user.id
        
        # Get the query (everything after /voz)
        user_query = ' '.join(context.args) if context.args else None
        
        if not user_query:
            await update.message.reply_text(
                "🔊 Usa: /voz [tu pregunta]\n\nEjemplo: /voz ¿Qué pasa si no pago una multa?"
            )
            return
        
        logger.info(f"Voice query from user {user_id}: {user_query}")
        await update.message.chat.send_action("typing")
        
        try:
            # Process through RAG pipeline
            rag_context = self.rag.get_context_for_query(user_query, n_results=5)
            response = self._generate_response(user_query, rag_context)
            
            # Send text response
            await update.message.reply_text(response)
            
            # Generate and send voice response
            with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as tmp_file:
                voice_path = tmp_file.name
            
            if self._text_to_speech(response, voice_path):
                try:
                    await update.message.chat.send_action("record_voice")
                    await update.message.reply_voice(voice=open(voice_path, "rb"))
                    logger.info(f"Sent voice response to user {user_id}")
                finally:
                    Path(voice_path).unlink(missing_ok=True)
            else:
                await update.message.reply_text("⚠️ No pude generar el audio, pero ahí está la respuesta en texto.")
                
        except Exception as e:
            logger.error(f"Error handling /voz command: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error. Por favor intenta de nuevo."
            )
    
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
        self.application.add_handler(CommandHandler("voz", self.voz_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        # Start polling
        logger.info("Bot is running. Press Ctrl+C to stop.")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def create_bot(rag_pipeline: RAGPipeline) -> TransitoBot:
    """Create and return a bot instance."""
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    return TransitoBot(rag_pipeline, telegram_token)
