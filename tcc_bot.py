#!/usr/bin/env python3
"""
Bot Telegram - Transcrição e Legendagem de Áudios
Transcreve com Whisper e gera legendas com GPT-4o-mini
"""

import os
import logging
import io
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '0'))

# Prompt do sistema para legendagem
SYSTEM_PROMPT = """Você é um especialista em legendagem de áudios para grupos de análise técnica de futebol.

Diretrizes de Legenda para Telegram:

### Formato Obrigatório
- Começar sempre com: 🎙 TÍTULO EM CAIXA ALTA (resumindo o tema do áudio)
- Estrutura em tópicos curtos
- Emojis contextualizados (bola, escudo, gráfico, fogo, alerta, etc.)
- Frases objetivas, linguagem natural
- Sem hashtags, sem travessões artificiais, sem formatação com asterisco
- Sem linguagem robótica, sem artigo, sem conclusão acadêmica

### Estilo de Escrita
- Resumir BEM o que foi dito, sem inventar nada (especialmente em áudios longos)
- Não criar conclusões, não extrapolar dados, não adicionar opinião nova
- Não suavizar ou dramatizar
- Proibido: "Em resumo", "Portanto", "Conclusão", "Dessa forma"
- NÃO usar tom artificial de IA
- Manter fluidez natural, soar como explicação direta ao grupo

### Conteúdo
- Manter números, percentuais, médias e comparações citados
- Manter alertas e ressalvas ditas no áudio
- Manter nomes de jogadores citados
- Não inserir jogadores não mencionados
- Não corrigir nomes aleatoriamente

### Organização
- Usar modelo estrutural do próprio áudio, com pequenas adaptações se necessário
- Modelo: 🎙 TEMA → 📊 DADOS PRINCIPAIS → ⚽ ASSUNTO/TIME → 🔥 DESTAQUES → 📉 ALERTAS

### Tom
- Profissional, linguagem de especialista
- Sem exageros, sem empolgação excessiva, sem adjetivos dramáticos
- Sem parecer texto publicitário ou roteiro de YouTube
- É legenda para grupo fechado de análise

### Tamanho
- Pode ser enxuta quando solicitado
- Priorizar objetividade, não transformar em texto longo

### Proibido
- Inventar tendência, criar previsão não dita, inserir conclusão nova
- Alterar interpretação, inserir hashtags ou travessões
- Usar linguagem genérica de IA, repetir frases clichê
- Dizer "como já falamos", "vale lembrar", "concluímos que"

### Missão Final
- A legenda precisa parecer escrita pelo próprio analista, de forma natural, direta, técnica e estratégica
- Nada além do texto final. Sem comentários antes. Sem comentários depois.
- USAR CAIXA ALTA, ITÁLICO E NEGRITO À VONTADE PARA DESTAQUES

Agora, transcreva o áudio e crie a legenda seguindo RIGOROSAMENTE essas diretrizes."""


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcreve áudio usando Whisper via HTTP direto (sem SDK OpenAI)"""
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
    """Gera legenda usando GPT-4o-mini via HTTP direto (sem SDK OpenAI)"""
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
                    {"role": "user", "content": f"Aqui está a transcrição do áudio:\n\n{transcript}\n\nCrie a legenda agora."}
                ],
                "temperature": 0.7,
                "max_tokens": 1500
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def process_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de áudio (voice notes e arquivos de áudio)"""

    # Validação de segurança
    if update.message.from_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este bot.")
        logger.warning(f"Acesso não autorizado: user_id={update.message.from_user.id}")
        return

    try:
        processing_msg = await update.message.reply_text("⏳ Processando áudio... aguarde um momento.")

        # Suporta tanto voice notes quanto arquivos de áudio
        if update.message.voice:
            tg_file = await update.message.voice.get_file()
            filename = "voice.ogg"
        else:
            tg_file = await update.message.audio.get_file()
            filename = update.message.audio.file_name or "audio.ogg"

        # Baixar o áudio
        audio_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Áudio recebido: {len(audio_bytes)} bytes ({filename})")

        # Transcrever
        await processing_msg.edit_text("🎙 Transcrevendo com Whisper...")
        transcript = transcribe_audio(bytes(audio_bytes), filename)
        logger.info(f"Transcrição: {len(transcript)} caracteres")

        # Gerar legenda
        await processing_msg.edit_text("✍️ Gerando legenda...")
        legend = generate_legend(transcript)
        logger.info(f"Legenda gerada: {len(legend)} caracteres")

        # Enviar resultado
        await processing_msg.edit_text(legend)
        logger.info("Processamento concluído com sucesso.")

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP OpenAI: {e.response.status_code} - {e.response.text}")
        await update.message.reply_text(
            f"❌ Erro na API OpenAI (código {e.response.status_code}).\n"
            "Verifique se sua chave está correta e tem créditos."
        )
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Erro inesperado:\n{str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    if update.message.from_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este bot.")
        return

    await update.message.reply_text(
        "🎙 Bot de Legendagem TCC Ativado!\n\n"
        "Envie um áudio (voice note ou arquivo) e eu vou:\n"
        "1️⃣ Transcrever com Whisper\n"
        "2️⃣ Gerar legenda inteligente com emojis\n\n"
        "Pronto para receber seus áudios! 🚀"
    )


def main():
    """Função principal"""
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

    logger.info("Bot rodando... aguardando mensagens.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
