#!/usr/bin/env python3
"""
Bot Telegram - Transcrição e Legendagem de Áudios
Compatível com Render Free (inclui servidor HTTP para health check)
"""

import os
import logging
import io
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))

SYSTEM_PROMPT = """Você é um analista de futebol experiente que cria legendas para áudios enviados em grupos fechados de Fantasy Game (Cartola FC). Sua escrita é direta, técnica, fluida e humana — jamais parece gerada por IA.

## FORMATAÇÃO OBRIGATÓRIA (Markdown do Telegram)

Use formatação Markdown nativa do Telegram:
- **negrito** com asteriscos duplos: **texto**
- _itálico_ com underscores: _texto_
- CAIXA ALTA para títulos de seção e nomes de destaque
- Emojis contextuais e funcionais (não decorativos)

Estrutura padrão:
🎙 **TÍTULO EM CAIXA ALTA** (tema central do áudio)

📊 **DADOS PRINCIPAIS**
- frase direta com dado concreto
- frase direta com dado concreto

⚽ **ASSUNTO/TIME**
- análise por time ou jogador mencionado

🔥 **DESTAQUES**
- **Nome do jogador** (Time/POS) — justificativa curta

📉 **ALERTAS**
- _ressalva ou cuidado mencionado no áudio_

## ESTILO DE ESCRITA

- Escreva como o próprio analista escreveria: direto, sem rodeios, com personalidade
- Use parágrafos curtos quando o raciocínio for mais analítico (não apenas bullet points)
- Alterne entre bullets e frases corridas conforme o ritmo do áudio
- Mantenha todos os números, médias, percentuais e comparações ditos no áudio
- Preserve o tom de alerta ou entusiasmo quando o analista demonstrar isso
- _Itálico_ para ressalvas, cautelas e observações subjetivas
- **Negrito** para nomes de jogadores em destaque, dados-chave e conclusões diretas

## PROIBIÇÕES ABSOLUTAS

- Não inventar dados, tendências ou jogadores não mencionados
- Não usar: "Em resumo", "Portanto", "Conclusão", "Dessa forma", "Vale lembrar", "Como já falamos"
- Não usar linguagem genérica de IA ou tom publicitário
- Não suavizar nem dramatizar além do que foi dito
- Não adicionar hashtags

## MISSÃO FINAL

A legenda deve parecer escrita pelo próprio analista — natural, técnica, estratégica.
Nada além do texto final. Sem comentários antes. Sem comentários depois."""


# ── Servidor HTTP para satisfazer o health check do Render ──────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot TCC Legendas rodando!")

    def log_message(self, format, *args):
        pass  # Silencia logs do servidor HTTP


def start_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    logger.info(f"Servidor HTTP rodando na porta {PORT}")
    server.serve_forever()


# ── Funções de transcrição e legendagem ─────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    audio_io = io.BytesIO(audio_bytes)
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_io, "audio/ogg")},
            data={"model": "whisper-1", "language": "pt"}
        )
        response.raise_for_status()
        return response.json()["text"]


def generate_legend(transcript: str) -> str:
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Transcrição do áudio:\n\n{transcript}\n\nCrie a legenda agora."}
                ],
                "temperature": 0.7,
                "max_tokens": 1500
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


# ── Handlers do Telegram ─────────────────────────────────────────────────────

async def process_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Mensagem recebida de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text(f"❌ Sem permissão. Seu ID é: {user_id}")
        return

    try:
        processing_msg = await update.message.reply_text("⏳ Processando áudio...")

        if update.message.voice:
            tg_file = await update.message.voice.get_file()
            filename = "voice.ogg"
        else:
            tg_file = await update.message.audio.get_file()
            filename = update.message.audio.file_name or "audio.ogg"

        audio_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Áudio recebido: {len(audio_bytes)} bytes")

        await processing_msg.edit_text("🎙 Transcrevendo...")
        transcript = transcribe_audio(bytes(audio_bytes), filename)
        logger.info(f"Transcrição: {len(transcript)} chars")

        await processing_msg.edit_text("✍️ Gerando legenda...")
        legend = generate_legend(transcript)
        logger.info(f"Legenda: {len(legend)} chars")

        await processing_msg.edit_text(legend, parse_mode='Markdown')
        logger.info("Concluído com sucesso.")

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro OpenAI: {e.response.status_code} - {e.response.text}")
        await update.message.reply_text(
            f"❌ Erro na API OpenAI (código {e.response.status_code}).\n"
            "Verifique se sua chave está correta e tem créditos."
        )
    except Exception as e:
        logger.error(f"Erro: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Comando /start de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text(f"❌ Sem permissão. Seu ID é: {user_id}")
        return
    await update.message.reply_text(
        "🎙 Bot de Legendagem TCC Ativado!\n\n"
        "Envie um áudio (voice note ou arquivo) e eu vou:\n"
        "1️⃣ Transcrever com Whisper\n"
        "2️⃣ Gerar legenda inteligente com emojis\n\n"
        "Pronto! 🚀"
    )


# ── Inicialização ─────────────────────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurado")
    if ALLOWED_USER_ID == 0:
        raise ValueError("ALLOWED_USER_ID não configurado")

    logger.info(f"Iniciando bot | ALLOWED_USER_ID={ALLOWED_USER_ID}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, process_audio_message))
    app.add_handler(MessageHandler(filters.AUDIO, process_audio_message))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Bot rodando... aguardando mensagens.")
    await asyncio.Event().wait()


if __name__ == '__main__':
    # Inicia o servidor HTTP em thread separada (para o Render não matar o processo)
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Inicia o bot
    asyncio.run(run_bot())
