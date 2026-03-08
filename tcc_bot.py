#!/usr/bin/env python3
"""
Bot Telegram para transcrição e legendagem de áudios
Transcreve com Whisper e gera legendas com GPT-4 mini
"""

import os
import logging
import requests
import io
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from openai import OpenAI

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

# Cliente OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

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


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa áudios enviados ao bot"""
    
    # Validação de segurança: apenas o usuário autorizado
    if update.message.from_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este bot.")
        logger.warning(f"Tentativa de acesso não autorizado do usuário {update.message.from_user.id}")
        return
    
    try:
        # Mensagem de processamento
        processing_msg = await update.message.reply_text("⏳ Processando áudio... (transcrição + legenda)")
        
        # Obter informações do áudio
        audio_file = await update.message.audio.get_file()
        
        # Baixar o arquivo de áudio
        audio_bytes = await audio_file.download_as_bytearray()
        audio_io = io.BytesIO(audio_bytes)
        audio_io.name = "audio.ogg"  # Telegram usa OGG
        
        logger.info(f"Áudio recebido: {len(audio_bytes)} bytes")
        
        # Transcrever com Whisper
        logger.info("Iniciando transcrição com Whisper...")
        transcript_response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_io,
            language="pt"
        )
        
        transcript_text = transcript_response.text
        logger.info(f"Transcrição concluída: {len(transcript_text)} caracteres")
        
        # Gerar legenda com GPT-4 mini
        logger.info("Gerando legenda com GPT-4 mini...")
        legend_response = client.chat.completions.create(
            model="gpt-4-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Aqui está a transcrição do áudio:\n\n{transcript_text}\n\nCrie a legenda agora."}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        legend_text = legend_response.choices[0].message.content
        logger.info(f"Legenda gerada: {len(legend_text)} caracteres")
        
        # Editar mensagem de processamento com o resultado
        await processing_msg.edit_text(legend_text)
        
        logger.info("Áudio processado com sucesso")
        
    except Exception as e:
        logger.error(f"Erro ao processar áudio: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ Erro ao processar áudio:\n{str(e)}"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    if update.message.from_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este bot.")
        return
    
    await update.message.reply_text(
        "🎙 **Bot de Legendagem TCC Ativado**\n\n"
        "Envie áudios que eu vou:\n"
        "1️⃣ Transcrever com Whisper\n"
        "2️⃣ Gerar legenda inteligente com emojis\n\n"
        "Pronto para receber seus áudios! 🚀"
    )


async def main():
    """Função principal"""
    
    # Validações
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurado")
    if ALLOWED_USER_ID == 0:
        raise ValueError("ALLOWED_USER_ID não configurado")
    
    logger.info(f"Iniciando bot com user_id: {ALLOWED_USER_ID}")
    
    # Criar aplicação
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(MessageHandler(filters.COMMAND, start))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    # Iniciar bot
    await application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
