"""
Telegram Bot for Colombian Transit Code Q&A
"""
import os
import logging
import tempfile
from typing import Optional
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from openai import OpenAI

from .rag import RAGPipeline
from .document_generator import DerechoPeticionGenerator
from . import analytics

# Admin user IDs (Telegram)
ADMIN_IDS = [935438639]  # Andres Garcia

# Conversation states for document generation
(SELECTING_TEMPLATE, NOMBRE, CEDULA, DIRECCION, TELEFONO, EMAIL, 
 CIUDAD, COMPARENDO, FECHA, PLACA, HECHOS, CONFIRMAR) = range(12)

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
        self.doc_generator = DerechoPeticionGenerator()
        self.application: Optional[Application] = None
        self.user_data = {}  # Store user document data during conversation
        
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
        user = update.effective_user
        user_id = user.id
        logger.info(f"Voice message from user {user_id}")
        
        # Check rate limit (10 messages per day)
        is_allowed, remaining = analytics.check_rate_limit(user_id, daily_limit=10, admin_ids=ADMIN_IDS)
        
        if not is_allowed:
            await update.message.reply_text(
                "❌ Has alcanzado el límite diario de 10 consultas.\n\n"
                "Por favor vuelve mañana para continuar usando el bot. 🕐\n\n"
                "Si necesitas acceso ilimitado, contacta al administrador."
            )
            logger.info(f"Rate limit exceeded for user {user_id}")
            return
        
        # Track analytics
        analytics.track_query(user.id, user.username, user.first_name, 'voice', '[voice message]')
        
        # Show remaining queries if getting close to limit
        if remaining <= 3 and remaining > 0:
            await update.message.reply_text(
                f"ℹ️ Te quedan {remaining} consulta{'s' if remaining > 1 else ''} hoy."
            )
        
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
        user = update.effective_user
        analytics.track_query(user.id, user.username, user.first_name, 'command', '/start')
        
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
/documento - Generar Derecho de Petición PDF 📄

**¿Cómo usar el bot?**
• Escribe tu pregunta → respuesta en texto
• Envía audio 🎤 → respuesta en texto + audio
• Usa /voz [pregunta] → respuesta en texto + audio
• Usa /documento → genera PDF para defenderte

**Tips para mejores respuestas:**
• Sé específico en tu pregunta
• Menciona el tema concreto (multas, velocidad, licencias, etc.)

**Ejemplos:**
• "¿Cuál es la multa por no usar cinturón?"
• /voz ¿Me pueden quitar la licencia por multas?
• /documento (para generar Derecho de Petición)
"""
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command - show usage statistics (admin only)."""
        if update.effective_user.id not in ADMIN_IDS:
            return  # Silently ignore non-admins
        
        stats = analytics.get_stats()
        
        # Format top users
        top_users_text = ""
        for i, u in enumerate(stats['top_users'][:5], 1):
            name = u['first_name'] or u['username'] or f"User {u['user_id']}"
            top_users_text += f"  {i}. {name}: {u['query_count']} consultas\n"
        
        # Format by type
        by_type_text = ""
        for qtype, count in stats['by_type'].items():
            emoji = {'text': '💬', 'voice': '🎤', 'command': '⚡', 'document': '📄'}.get(qtype, '•')
            by_type_text += f"  {emoji} {qtype}: {count}\n"
        
        stats_message = f"""📊 **Estadísticas del Bot**

**Totales:**
• Consultas totales: {stats['total_queries']}
• Usuarios únicos: {stats['unique_users']}
• Hoy: {stats['today_queries']} consultas
• Esta semana: {stats['week_queries']} consultas

**Por tipo:**
{by_type_text}
**Top usuarios:**
{top_users_text if top_users_text else '  (sin datos aún)'}

**Usuarios recientes (24h):** {len(stats['recent_users'])}
"""
        await update.message.reply_text(stats_message, parse_mode='Markdown')
    
    async def voz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /voz command - respond with text AND voice."""
        user = update.effective_user
        user_id = user.id
        
        # Get the query (everything after /voz)
        user_query = ' '.join(context.args) if context.args else None
        
        if not user_query:
            await update.message.reply_text(
                "🔊 Usa: /voz [tu pregunta]\n\nEjemplo: /voz ¿Qué pasa si no pago una multa?"
            )
            return
        
        # Check rate limit (10 messages per day)
        is_allowed, remaining = analytics.check_rate_limit(user_id, daily_limit=10, admin_ids=ADMIN_IDS)
        
        if not is_allowed:
            await update.message.reply_text(
                "❌ Has alcanzado el límite diario de 10 consultas.\n\n"
                "Por favor vuelve mañana para continuar usando el bot. 🕐\n\n"
                "Si necesitas acceso ilimitado, contacta al administrador."
            )
            logger.info(f"Rate limit exceeded for user {user_id}")
            return
        
        # Track analytics
        analytics.track_query(user.id, user.username, user.first_name, 'command', f'/voz {user_query}')
        
        # Show remaining queries if getting close to limit
        if remaining <= 3 and remaining > 0:
            await update.message.reply_text(
                f"ℹ️ Te quedan {remaining} consulta{'s' if remaining > 1 else ''} hoy."
            )
        
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
        user = update.effective_user
        user_id = user.id
        logger.info(f"Query from user {user_id}: {user_query}")
        
        # Check rate limit (10 messages per day)
        is_allowed, remaining = analytics.check_rate_limit(user_id, daily_limit=10, admin_ids=ADMIN_IDS)
        
        if not is_allowed:
            await update.message.reply_text(
                "❌ Has alcanzado el límite diario de 10 consultas.\n\n"
                "Por favor vuelve mañana para continuar usando el bot. 🕐\n\n"
                "Si necesitas acceso ilimitado, contacta al administrador."
            )
            logger.info(f"Rate limit exceeded for user {user_id}")
            return
        
        # Track analytics
        analytics.track_query(user.id, user.username, user.first_name, 'text', user_query)
        
        # Show remaining queries if getting close to limit
        if remaining <= 3 and remaining > 0:
            await update.message.reply_text(
                f"ℹ️ Te quedan {remaining} consulta{'s' if remaining > 1 else ''} hoy.",
                reply_to_message_id=update.message.message_id
            )
        
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
    
    # ============= DOCUMENT GENERATION CONVERSATION =============
    
    async def documento_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start document generation - /documento command."""
        keyboard = [
            [InlineKeyboardButton("📅 Prescripción (multa > 3 años)", callback_data="doc_prescripcion")],
            [InlineKeyboardButton("📬 Sin notificación oportuna", callback_data="doc_fotomulta_notificacion")],
            [InlineKeyboardButton("👤 No identifican al conductor", callback_data="doc_fotomulta_identificacion")],
            [InlineKeyboardButton("🚫 Sin señalización (500m)", callback_data="doc_fotomulta_señalizacion")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="doc_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📄 *GENERAR DERECHO DE PETICIÓN*\n\n"
            "Selecciona el tipo de documento que necesitas:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SELECTING_TEMPLATE
    
    async def template_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle template selection."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "doc_cancel":
            await query.edit_message_text("❌ Generación de documento cancelada.")
            return ConversationHandler.END
        
        template_type = query.data.replace("doc_", "")
        user_id = update.effective_user.id
        self.user_data[user_id] = {"template": template_type}
        
        templates_names = {
            "prescripcion": "Prescripción de multa",
            "fotomulta_notificacion": "Nulidad por falta de notificación",
            "fotomulta_identificacion": "Nulidad por no identificar conductor",
            "fotomulta_señalizacion": "Nulidad por falta de señalización"
        }
        
        await query.edit_message_text(
            f"✅ Tipo: *{templates_names.get(template_type, template_type)}*\n\n"
            "Ahora necesito tus datos. Escribe tu *nombre completo*:",
            parse_mode='Markdown'
        )
        return NOMBRE
    
    async def get_nombre(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["nombre"] = update.message.text
        await update.message.reply_text("📝 Escribe tu *número de cédula*:", parse_mode='Markdown')
        return CEDULA
    
    async def get_cedula(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["cedula"] = update.message.text
        await update.message.reply_text("🏠 Escribe tu *dirección completa* (para notificaciones):", parse_mode='Markdown')
        return DIRECCION
    
    async def get_direccion(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["direccion"] = update.message.text
        await update.message.reply_text("📱 Escribe tu *número de teléfono*:", parse_mode='Markdown')
        return TELEFONO
    
    async def get_telefono(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["telefono"] = update.message.text
        await update.message.reply_text("📧 Escribe tu *correo electrónico*:", parse_mode='Markdown')
        return EMAIL
    
    async def get_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["email"] = update.message.text
        await update.message.reply_text("🏙️ ¿En qué *ciudad* está la autoridad de tránsito? (ej: Bogotá D.C., Medellín):", parse_mode='Markdown')
        return CIUDAD
    
    async def get_ciudad(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["ciudad"] = update.message.text
        await update.message.reply_text("🔢 Escribe el *número del comparendo/multa*:", parse_mode='Markdown')
        return COMPARENDO
    
    async def get_comparendo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["comparendo"] = update.message.text
        await update.message.reply_text("📅 ¿Cuál fue la *fecha de la infracción*? (ej: 15 de enero de 2022):", parse_mode='Markdown')
        return FECHA
    
    async def get_fecha(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["fecha"] = update.message.text
        await update.message.reply_text("🚗 Escribe la *placa del vehículo*:", parse_mode='Markdown')
        return PLACA
    
    async def get_placa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["placa"] = update.message.text
        await update.message.reply_text(
            "📝 Describe brevemente los *hechos adicionales* de tu caso.\n"
            "(Ej: 'Nunca recibí notificación', 'La cámara no tenía señalización', etc.)\n\n"
            "Escribe /saltar si no tienes hechos adicionales.",
            parse_mode='Markdown'
        )
        return HECHOS
    
    async def get_hechos(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text = update.message.text
        self.user_data[user_id]["hechos"] = "" if text == "/saltar" else text
        
        data = self.user_data[user_id]
        # Use plain text to avoid Markdown parsing issues with user input
        resumen = f"""📄 RESUMEN DE TU DOCUMENTO

👤 Nombre: {data['nombre']}
🆔 Cédula: {data['cedula']}
🏠 Dirección: {data['direccion']}
📱 Teléfono: {data['telefono']}
📧 Email: {data['email']}
🏙️ Ciudad autoridad: {data['ciudad']}
🔢 Comparendo: {data['comparendo']}
📅 Fecha infracción: {data['fecha']}
🚗 Placa: {data['placa']}

¿Generar el documento PDF?"""
        keyboard = [
            [InlineKeyboardButton("✅ Generar PDF", callback_data="doc_generar")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="doc_cancel_final")]
        ]
        await update.message.reply_text(resumen, reply_markup=InlineKeyboardMarkup(keyboard))
        return CONFIRMAR
    
    async def generar_documento(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Generate and send the PDF document."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "doc_cancel_final":
            user_id = update.effective_user.id
            if user_id in self.user_data:
                del self.user_data[user_id]
            await query.edit_message_text("❌ Generación cancelada.")
            return ConversationHandler.END
        
        user_id = update.effective_user.id
        data = self.user_data.get(user_id, {})
        
        await query.edit_message_text("⏳ Generando tu documento PDF...")
        
        try:
            pdf_buffer = self.doc_generator.generate_document(
                template_type=data['template'],
                nombre_completo=data['nombre'],
                cedula=data['cedula'],
                direccion=data['direccion'],
                telefono=data['telefono'],
                email=data['email'],
                ciudad_autoridad=data['ciudad'],
                numero_comparendo=data['comparendo'],
                fecha_infraccion=data['fecha'],
                placa_vehiculo=data['placa'],
                hechos_adicionales=data.get('hechos', '')
            )
            
            filename = f"Derecho_Peticion_{data['comparendo'].replace(' ', '_')}.pdf"
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=pdf_buffer,
                filename=filename,
                caption="📄 *¡Tu Derecho de Petición está listo!*\n\n"
                        "✅ Imprímelo y fírmalo\n"
                        "✅ Radícalo en la Secretaría de Tránsito\n"
                        "✅ Guarda copia con sello de radicado\n"
                        "✅ Tienen 15 días hábiles para responder",
                parse_mode='Markdown'
            )
            
            logger.info(f"Generated document for user {user_id}: {filename}")
            
        except Exception as e:
            logger.error(f"Error generating document: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Error generando el documento. Por favor intenta de nuevo."
            )
        
        # Clean up user data
        if user_id in self.user_data:
            del self.user_data[user_id]
        
        return ConversationHandler.END
    
    async def cancel_documento(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel document generation."""
        user_id = update.effective_user.id
        if user_id in self.user_data:
            del self.user_data[user_id]
        await update.message.reply_text("❌ Generación de documento cancelada.")
        return ConversationHandler.END
    
    # ============= END DOCUMENT GENERATION =============
    
    def run(self) -> None:
        """Run the bot."""
        logger.info("Starting Transito HP Bot...")
        
        # Create application
        self.application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("voz", self.voz_command))
        
        # Document generation conversation handler
        doc_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("documento", self.documento_command)],
            states={
                SELECTING_TEMPLATE: [CallbackQueryHandler(self.template_selected)],
                NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_nombre)],
                CEDULA: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_cedula)],
                DIRECCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_direccion)],
                TELEFONO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_telefono)],
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_email)],
                CIUDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_ciudad)],
                COMPARENDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_comparendo)],
                FECHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_fecha)],
                PLACA: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_placa)],
                HECHOS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_hechos),
                    CommandHandler("saltar", self.get_hechos)
                ],
                CONFIRMAR: [CallbackQueryHandler(self.generar_documento)],
            },
            fallbacks=[CommandHandler("cancelar", self.cancel_documento)],
        )
        self.application.add_handler(doc_conv_handler)
        
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
