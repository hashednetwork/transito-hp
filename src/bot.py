"""
TransitoColBot - Telegram Bot for Colombian Transit Law Q&A
Enhanced version with comprehensive RAG, voice, and document generation
"""
import os
import logging
import tempfile
from typing import Optional, Tuple
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode, ChatAction
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

# Rate limit configuration
DAILY_QUERY_LIMIT = 10  # Free tier limit

# Enhanced System Prompt with comprehensive legal knowledge
SYSTEM_PROMPT = """Eres un asistente legal especializado en normativa de tránsito de Colombia. Tu nombre es TransitoColBot.

## FUENTES NORMATIVAS QUE CONOCES:

### Jerarquía Normativa (de mayor a menor fuerza vinculante):

1. **CONSTITUCIÓN POLÍTICA (Fuerza máxima)**
   - Art. 24: Derecho a circular libremente con limitaciones legales
   - Art. 23: Derecho de petición (respuesta en 15 días hábiles)
   - Art. 29: Debido proceso (presunción de inocencia, defensa, pruebas)

2. **LEYES Y CÓDIGOS (Fuerza alta)**
   - Ley 769 de 2002: Código Nacional de Tránsito Terrestre (eje normativo principal)
   - Ley 1383 de 2010: Reforma al Código de Tránsito
   - Ley 1696 de 2013: Sanciones por embriaguez
   - Ley 1843 de 2017: Sistemas de fotodetección (señalización 500m, notificación 3 días)
   - Ley 2251 de 2022: "Ley Julián Esteban" - Velocidad y Sistema Seguro
   - Ley 2393 de 2024: Cinturón de seguridad en transporte escolar
   - Ley 2435 de 2024: Ajustes sancionatorios
   - Ley 2486 de 2025: Vehículos eléctricos de movilidad personal

3. **DECRETOS (Reglamentarios/compilatorios)**
   - Decreto 1079 de 2015: Decreto Único Reglamentario del sector transporte (hub de reglamentaciones)
   - Decreto 2106 de 2019: Simplificación de trámites (documentos digitales, Art. 111)
   - Decreto 1430 de 2022: Plan Nacional de Seguridad Vial 2022-2031 (Sistema Seguro)

4. **RESOLUCIONES (Técnicas/administrativas)**
   - Resolución 20223040045295 de 2022: Resolución Única Compilatoria del MinTransporte
   - Resolución 20243040045005 de 2024: Manual de Señalización Vial 2024 (Anexo 76)
   - Resolución 20233040025995 de 2023: Metodología para velocidad límite
   - Resolución 20233040025895 de 2023: Planes de gestión de velocidad
   - Resolución 20203040023385 de 2020: Condiciones de uso del casco
   - Resolución 20203040011245 de 2020: Criterios técnicos SAST/fotodetección (CLAVE para legalidad)
   - Resolución 20223040040595 de 2022: Metodología PESV

5. **JURISPRUDENCIA (Interpretativa/condicionante)**
   - C-530 de 2003: Debido proceso; ayudas tecnológicas condicionadas
   - C-980 de 2010: Notificación debe garantizar conocimiento efectivo
   - C-038 de 2020: Responsabilidad PERSONAL en fotomultas (NO al propietario automáticamente)
   - Concepto Sala de Consulta Rad. 2433/2020: Marco jurídico de fotomultas/privados

6. **CIRCULARES (Lineamientos operativos)**
   - Circular Conjunta 023/2025: Plan 365 (pedagogía y control)
   - Circular Externa 20254000000867: SAST y control de señalización (Supertransporte)

7. **GUÍAS PRÁCTICAS:** Señor Biter (defensa de derechos del conductor)

## TU ROL:
- Responder ÚNICAMENTE basándote en el contexto proporcionado y tu conocimiento de las normas
- Citar artículos y normas específicas (ej: "Según el Artículo 131 de la Ley 769...")
- Dar consejos PRÁCTICOS sobre cómo defender derechos del conductor
- Responder siempre en ESPAÑOL
- Ser preciso, claro y conciso
- NO inventar información que no esté en las fuentes

## DERECHOS CLAVE DEL CONDUCTOR QUE DEBES ENFATIZAR:
1. **Documentos digitales:** Las autoridades NO pueden exigir documentos físicos si pueden consultarlos en RUNT (Decreto 2106 de 2019, Art. 111)
2. **Fotomultas:**
   - Deben notificarse en 3 días hábiles máximo
   - Requieren señalización 500m antes
   - Deben identificar al conductor (NO responsabilidad automática del propietario - C-038/2020)
   - La cámara debe estar autorizada por la Agencia Nacional de Seguridad Vial
3. **Prescripción:** Las multas prescriben en 3 AÑOS desde la infracción
4. **Descuentos:** 50% primeros 5 días, 25% días 6-20
5. **Debido proceso:** Derecho a ser notificado, conocer pruebas, controvertir, interponer recursos

## FORMATO DE RESPUESTA:
- Usa viñetas y estructura clara
- Cita la norma específica
- Da pasos concretos cuando aplique
- Si no tienes la información, indica que no la tienes en tu base de conocimiento

Recuerda: Eres un asistente informativo, no un abogado. Sugiere consultar profesional para casos complejos."""

# Shortened prompt for voice responses
VOICE_SYSTEM_PROMPT = """Eres TransitoColBot, asistente de tránsito colombiano. Responde de forma conversacional y clara para audio.
- Sé conciso pero informativo
- Cita las normas relevantes
- Habla de forma natural, como explicándole a un amigo
- Máximo 3-4 puntos clave por respuesta"""


class TransitoBot:
    """
    Enhanced Telegram Bot for Colombian Transit Law.
    Features:
    - Multi-source RAG retrieval
    - Voice input (Whisper) and output (TTS)
    - PDF document generation
    - Rate limiting and analytics
    """
    
    def __init__(self, rag_pipeline: RAGPipeline, telegram_token: str):
        """Initialize the Telegram bot with RAG pipeline."""
        self.rag = rag_pipeline
        self.telegram_token = telegram_token
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.doc_generator = DerechoPeticionGenerator()
        self.application: Optional[Application] = None
        self.user_data = {}  # Store user document data during conversation
        
        # LLM configuration
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1200"))
        
        logger.info(f"Bot initialized with model: {self.llm_model}")
    
    def _generate_response(
        self, 
        query: str, 
        context: str,
        system_prompt: str = SYSTEM_PROMPT,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate a response using the LLM with retrieved context."""
        user_message = f"""## Contexto de la Base de Conocimiento:

{context}

---

## Pregunta del usuario:
{query}

Responde basándote en el contexto proporcionado. Si la información no está disponible, indícalo claramente."""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.llm_temperature,
                max_tokens=max_tokens or self.llm_max_tokens
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
                    language="es"
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise
    
    def _text_to_speech(self, text: str, output_path: str) -> bool:
        """Convert text to speech using OpenAI TTS API."""
        try:
            # Limit text length for TTS
            if len(text) > 4000:
                text = text[:4000] + "... Para más detalles, lee el mensaje de texto."
            
            # Clean text for better TTS
            text = self._clean_text_for_tts(text)
            
            response = self.openai_client.audio.speech.create(
                model="tts-1",
                voice="nova",  # Clear Spanish pronunciation
                input=text,
                response_format="opus"
            )
            
            response.stream_to_file(output_path)
            return True
        except Exception as e:
            logger.error(f"Error generating TTS: {e}")
            return False
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text for better TTS output."""
        import re
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Code
        text = re.sub(r'#{1,6}\s*', '', text)  # Headers
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
        # Clean up bullets
        text = re.sub(r'^[-•]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
        return text.strip()
    
    async def _check_rate_limit(self, user_id: int) -> Tuple[bool, int]:
        """Check rate limit and return (is_allowed, remaining)."""
        return analytics.check_rate_limit(
            user_id, 
            daily_limit=DAILY_QUERY_LIMIT, 
            admin_ids=ADMIN_IDS
        )
    
    async def _send_rate_limit_message(self, update: Update):
        """Send rate limit exceeded message."""
        await update.message.reply_text(
            "❌ *Has alcanzado el límite diario de 10 consultas.*\n\n"
            "Por favor vuelve mañana para continuar usando el bot. 🕐\n\n"
            "💡 _Tip: Si necesitas acceso ilimitado, contacta al administrador._",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _send_remaining_warning(self, update: Update, remaining: int):
        """Send warning about remaining queries."""
        if remaining <= 3 and remaining > 0:
            await update.message.reply_text(
                f"ℹ️ Te quedan *{remaining}* consulta{'s' if remaining > 1 else ''} hoy.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    # ==================== COMMAND HANDLERS ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user = update.effective_user
        analytics.track_query(user.id, user.username, user.first_name, 'command', '/start')
        
        welcome_message = """🚗 *¡Bienvenido a TransitoColBot!*

Soy tu asistente especializado en normativa de tránsito colombiana. Te ayudo con:

📚 *Base de Conocimiento:*
• Código Nacional de Tránsito (Ley 769/2002)
• Decreto 2106/2019 (documentos digitales)
• Ley 1843/2017 (fotomultas)
• Jurisprudencia constitucional (C-038/2020)
• Leyes 2024-2025 (actualizado)

🎯 *¿Cómo puedo ayudarte?*
Escribe tu pregunta o envía un audio 🎤

✍️ *Ejemplos:*
• "¿Me pueden exigir documentos físicos?"
• "¿Cómo tumbar una fotomulta?"
• "¿Las multas prescriben?"
• "¿Qué dice la Sentencia C-038?"

📄 *Comandos útiles:*
/documento - Generar Derecho de Petición PDF
/voz - Respuesta en texto + audio
/help - Más información

¡Hazme tu pregunta!"""
        
        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_message = """📖 *Ayuda - TransitoColBot*

*Comandos disponibles:*
/start - Mensaje de bienvenida
/help - Esta ayuda
/voz [pregunta] - Respuesta en texto + audio 🔊
/documento - Generar Derecho de Petición PDF 📄
/fuentes - Ver fuentes normativas
/stats - Estadísticas (solo admin)

*¿Cómo usar el bot?*
• Escribe tu pregunta → respuesta en texto
• Envía audio 🎤 → respuesta en texto + audio
• Usa /voz [pregunta] → respuesta en texto + audio
• Usa /documento → genera PDF para defenderte

*Tips para mejores respuestas:*
• Sé específico en tu pregunta
• Menciona el tema (multas, fotomultas, prescripción, documentos)
• Pregunta por normas específicas si las conoces

*Temas que domino:*
🚦 Infracciones y multas
📸 Fotomultas y cómo impugnarlas
📋 Documentos (licencia, SOAT, RTM)
⏰ Prescripción de multas
⚖️ Jurisprudencia relevante
📝 Derechos de petición

*Límites:*
• 10 consultas diarias (tier gratuito)
• Admins tienen acceso ilimitado"""
        
        await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    async def fuentes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /fuentes command - show indexed sources and normative hierarchy."""
        stats = self.rag.get_stats()
        
        fuentes_text = """📚 *Fuentes Normativas Indexadas*

*JERARQUÍA NORMATIVA:*

🏛️ *1. Constitución (Fuerza máxima):*
• Art. 24 - Libertad de circulación
• Art. 23 - Derecho de petición
• Art. 29 - Debido proceso

⚖️ *2. Leyes (Fuerza alta):*
• Ley 769/2002 - Código de Tránsito
• Ley 1843/2017 - Fotodetección
• Ley 2393/2024 - Cinturón escolar
• Ley 2435/2024 - Ajustes sancionatorios
• Ley 2486/2025 - Vehículos eléctricos

📋 *3. Decretos (Reglamentarios):*
• Decreto 1079/2015 - DUR Transporte
• Decreto 2106/2019 - Simplificación trámites

📄 *4. Resoluciones:*
• Res. 20223040045295/2022 - Compilatoria
• Manual Señalización 2024

⚖️ *5. Jurisprudencia:*
• C-530/2003 - Debido proceso
• C-980/2010 - Notificación
• C-038/2020 - Responsabilidad personal

📖 *6. Guías:*
• Compendio Normativo 2024-2025
• Inventario de Documentos
• Guías Señor Biter

📊 *Estadísticas del RAG:*
"""
        
        total = stats.get('total_chunks', 0)
        fuentes_text += f"Total fragmentos: {total}\n"
        
        by_source = stats.get('by_source', {})
        for source, count in by_source.items():
            if count > 0:
                fuentes_text += f"• {source}: {count}\n"
        
        await update.message.reply_text(fuentes_text, parse_mode=ParseMode.MARKDOWN)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command - show usage statistics (admin only)."""
        if update.effective_user.id not in ADMIN_IDS:
            return
        
        stats = analytics.get_stats()
        rag_stats = self.rag.get_stats()
        
        # Format top users
        top_users_text = ""
        for i, u in enumerate(stats['top_users'][:5], 1):
            name = u['first_name'] or u['username'] or f"User {u['user_id']}"
            top_users_text += f"  {i}. {name}: {u['query_count']} consultas\n"
        
        # Format by type
        by_type_text = ""
        type_emojis = {'text': '💬', 'voice': '🎤', 'command': '⚡', 'document': '📄'}
        for qtype, count in stats['by_type'].items():
            emoji = type_emojis.get(qtype, '•')
            by_type_text += f"  {emoji} {qtype}: {count}\n"
        
        stats_message = f"""📊 *Estadísticas del Bot*

*Totales:*
• Consultas totales: {stats['total_queries']}
• Usuarios únicos: {stats['unique_users']}
• Hoy: {stats['today_queries']} consultas
• Esta semana: {stats['week_queries']} consultas

*Por tipo:*
{by_type_text}

*Top usuarios:*
{top_users_text if top_users_text else '  (sin datos)'}

*RAG:*
• Modelo: {self.llm_model}
• Chunks indexados: {rag_stats['total_chunks']}

*Usuarios recientes (24h):* {len(stats['recent_users'])}
"""
        await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
    
    async def voz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /voz command - respond with text AND voice."""
        user = update.effective_user
        user_id = user.id
        
        user_query = ' '.join(context.args) if context.args else None
        
        if not user_query:
            await update.message.reply_text(
                "🔊 *Uso:* /voz [tu pregunta]\n\n"
                "*Ejemplo:* /voz ¿Qué pasa si no pago una multa?",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Rate limit check
        is_allowed, remaining = await self._check_rate_limit(user_id)
        if not is_allowed:
            await self._send_rate_limit_message(update)
            return
        
        analytics.track_query(user.id, user.username, user.first_name, 'command', f'/voz {user_query}')
        await self._send_remaining_warning(update, remaining)
        
        logger.info(f"Voice query from user {user_id}: {user_query}")
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            # Process through RAG pipeline
            rag_context = self.rag.get_context_for_query(user_query, n_results=5)
            
            # Generate text response
            response = self._generate_response(user_query, rag_context)
            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
            
            # Generate voice response with conversational prompt
            voice_response = self._generate_response(
                user_query, 
                rag_context, 
                system_prompt=VOICE_SYSTEM_PROMPT,
                max_tokens=600
            )
            
            with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as tmp_file:
                voice_path = tmp_file.name
            
            if self._text_to_speech(voice_response, voice_path):
                try:
                    await update.message.chat.send_action(ChatAction.RECORD_VOICE)
                    await update.message.reply_voice(voice=open(voice_path, "rb"))
                    logger.info(f"Sent voice response to user {user_id}")
                finally:
                    Path(voice_path).unlink(missing_ok=True)
            else:
                await update.message.reply_text(
                    "⚠️ No pude generar el audio, pero ahí está la respuesta en texto."
                )
                
        except Exception as e:
            logger.error(f"Error handling /voz command: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error. Por favor intenta de nuevo."
            )
    
    # ==================== MESSAGE HANDLERS ====================
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming voice messages."""
        user = update.effective_user
        user_id = user.id
        logger.info(f"Voice message from user {user_id}")
        
        # Rate limit check
        is_allowed, remaining = await self._check_rate_limit(user_id)
        if not is_allowed:
            await self._send_rate_limit_message(update)
            return
        
        analytics.track_query(user.id, user.username, user.first_name, 'voice', '[voice message]')
        await self._send_remaining_warning(update, remaining)
        
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            # Download voice file
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
                tmp_path = tmp_file.name
                await file.download_to_drive(tmp_path)
            
            try:
                # Transcribe audio
                logger.info(f"Transcribing voice message from user {user_id}")
                transcribed_text = self._transcribe_audio(tmp_path)
                logger.info(f"Transcribed: {transcribed_text[:100]}...")
                
                # Show user what we understood
                await update.message.reply_text(
                    f"🎤 *Entendí:* _{transcribed_text}_\n\n⏳ Buscando respuesta...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Process through RAG pipeline
                rag_context = self.rag.get_context_for_query(transcribed_text, n_results=5)
                response = self._generate_response(transcribed_text, rag_context)
                
                # Send text response
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
                
                # Generate and send voice response
                voice_response = self._generate_response(
                    transcribed_text,
                    rag_context,
                    system_prompt=VOICE_SYSTEM_PROMPT,
                    max_tokens=600
                )
                
                voice_path = tmp_path.replace(".ogg", "_response.opus")
                if self._text_to_speech(voice_response, voice_path):
                    try:
                        await update.message.reply_voice(voice=open(voice_path, "rb"))
                        logger.info(f"Sent voice response to user {user_id}")
                    finally:
                        Path(voice_path).unlink(missing_ok=True)
                
            finally:
                Path(tmp_path).unlink(missing_ok=True)
                
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error procesando tu mensaje de voz. "
                "Por favor intenta de nuevo o escribe tu pregunta."
            )
    
    async def derecho_peticion_trigger(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger /documento for 'derecho de peticion' queries."""
        await update.message.reply_text(
            "📄 Para crear un *Derecho de Petición*, usa el comando /documento\n\n"
            "Te guiaré paso a paso para generar tu PDF personalizado:\n"
            "• Selecciona tipo (prescripción, fotomulta, etc.)\n"
            "• Ingresa tus datos\n"
            "• Descarga PDF listo para radicar\n\n"
            "¡Empieza con /documento ahora!",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages."""
        user_query = update.message.text
        user = update.effective_user
        user_id = user.id
        logger.info(f"Query from user {user_id}: {user_query}")
        
        # Rate limit check
        is_allowed, remaining = await self._check_rate_limit(user_id)
        if not is_allowed:
            await self._send_rate_limit_message(update)
            return
        
        analytics.track_query(user.id, user.username, user.first_name, 'text', user_query)
        await self._send_remaining_warning(update, remaining)
        
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            # Retrieve relevant context from RAG
            rag_context = self.rag.get_context_for_query(user_query, n_results=5)
            
            # Generate response
            response = self._generate_response(user_query, rag_context)
            
            # Send response (handle markdown errors gracefully)
            try:
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback to plain text if markdown fails
                await update.message.reply_text(response)
            
            logger.info(f"Sent response to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "Lo siento, hubo un error procesando tu pregunta. Por favor intenta de nuevo más tarde."
            )
    
    # ==================== DOCUMENT GENERATION ====================
    
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
            "Selecciona el tipo de documento que necesitas:\n\n"
            "_Cada tipo está fundamentado en la normativa colombiana vigente._",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
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
            "prescripcion": "Prescripción de multa (Art. 159 Ley 769)",
            "fotomulta_notificacion": "Nulidad por falta de notificación (Art. 8 Ley 1843)",
            "fotomulta_identificacion": "Nulidad por no identificar conductor (C-038/2020)",
            "fotomulta_señalizacion": "Nulidad por falta de señalización (Art. 5 Ley 1843)"
        }
        
        await query.edit_message_text(
            f"✅ Tipo: *{templates_names.get(template_type, template_type)}*\n\n"
            "Ahora necesito tus datos. Escribe tu *nombre completo*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return NOMBRE
    
    async def get_nombre(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["nombre"] = update.message.text
        await update.message.reply_text(
            "📝 Escribe tu *número de cédula*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return CEDULA
    
    async def get_cedula(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["cedula"] = update.message.text
        await update.message.reply_text(
            "🏠 Escribe tu *dirección completa* (para notificaciones):",
            parse_mode=ParseMode.MARKDOWN
        )
        return DIRECCION
    
    async def get_direccion(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["direccion"] = update.message.text
        await update.message.reply_text(
            "📱 Escribe tu *número de teléfono*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return TELEFONO
    
    async def get_telefono(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["telefono"] = update.message.text
        await update.message.reply_text(
            "📧 Escribe tu *correo electrónico*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return EMAIL
    
    async def get_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["email"] = update.message.text
        await update.message.reply_text(
            "🏙️ ¿En qué *ciudad* está la autoridad de tránsito?\n"
            "_Ejemplo: Bogotá D.C., Medellín, Cali_",
            parse_mode=ParseMode.MARKDOWN
        )
        return CIUDAD
    
    async def get_ciudad(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["ciudad"] = update.message.text
        await update.message.reply_text(
            "🔢 Escribe el *número del comparendo/multa*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return COMPARENDO
    
    async def get_comparendo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["comparendo"] = update.message.text
        await update.message.reply_text(
            "📅 ¿Cuál fue la *fecha de la infracción*?\n"
            "_Ejemplo: 15 de enero de 2022_",
            parse_mode=ParseMode.MARKDOWN
        )
        return FECHA
    
    async def get_fecha(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["fecha"] = update.message.text
        await update.message.reply_text(
            "🚗 Escribe la *placa del vehículo*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return PLACA
    
    async def get_placa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        self.user_data[user_id]["placa"] = update.message.text
        await update.message.reply_text(
            "📝 Describe brevemente los *hechos adicionales* de tu caso.\n\n"
            "_Ejemplo: 'Nunca recibí notificación', 'La cámara no tenía señalización'_\n\n"
            "Escribe /saltar si no tienes hechos adicionales.",
            parse_mode=ParseMode.MARKDOWN
        )
        return HECHOS
    
    async def get_hechos(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text = update.message.text
        self.user_data[user_id]["hechos"] = "" if text == "/saltar" else text
        
        data = self.user_data[user_id]
        resumen = f"""📄 *RESUMEN DE TU DOCUMENTO*

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
        await update.message.reply_text(
            resumen, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
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
        
        # Track document generation
        analytics.track_query(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
            'document',
            f"template:{data.get('template', 'unknown')}"
        )
        
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
                        "✅ Tienen 15 días hábiles para responder\n\n"
                        "_Documento generado con fundamentos de la normativa colombiana vigente._",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Generated document for user {user_id}: {filename}")
            
        except Exception as e:
            logger.error(f"Error generating document: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Error generando el documento. Por favor intenta de nuevo."
            )
        
        # Clean up
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
    
    # ==================== BOT RUNNER ====================
    
    def run(self) -> None:
        """Run the bot."""
        logger.info("Starting TransitoColBot...")
        
        # Create application
        self.application = Application.builder().token(self.telegram_token).build()
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("fuentes", self.fuentes_command))
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
        
        # Message handlers (order matters!)
        self.application.add_handler(
            MessageHandler(
                filters.Regex(r'(?i)(derecho.*peticion|crear.*(derecho.*peticion|documento)|peticion.*derecho)'),
                self.derecho_peticion_trigger
            )
        )
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
