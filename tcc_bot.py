#!/usr/bin/env python3
"""
Bot Telegram - Transcrição e Legendagem de Áudios
Compatível com Railway/Render (inclui servidor HTTP para health check)
Usa HTML parse_mode para formatação confiável
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

# Lista de jogadores (apenas nomes para otimizar tokens)
JOGADORES_LIST = """
Abel Ferreira, Acevedo, Ademir, Adonis Frías, Adson, Aguirre, Alan Franco, Alan Patrick, Alan Rodríguez, Alerrandro, Alef Manga, Alessandro, Alex Sandro, Alex Telles, Alexander Barboza, Alexsander, Alisson, Alix Vinicius, Allan, Allan, Allex, Almir, Aloísio, Anderson, André, André, André Luis, André Ramalho, Andreas Pereira, Andrew, Andrey Fernandes, Angileri, Anthoni, Antonini, Antony, Arão, Ararat, Arboleda, Arias, Arthur, Arthur Cabral, Arthur Dias, Arthur Izaque, Arthur Melo, Arthur Novaes, Artur, Arrascaeta, Ayrton Lucas, Bastos, Batata, Belé, Benassi, Benavídez, Benedetti, Bernal, Bernabei, Bernard, Bobadilla, Bolasie, Borré, Braithwaite, Brayan, Breno Bidon, Breno Lopes, Bruno Alves, Bruno Fuchs, Bruno Gomes, Bruno Henrique, Bruno Henrique, Bruno Leonardo, Bruno Melo, Bruno Pacheco, Bruno Rodrigues, Bruno Tabata, Bruninho, Cacá, Caio Alexandre, Caio Paulista, Caíque, Calleri, Camilo, Camutanga, Canobbio, Cantalapiedra, Cantillo, Carlos Cuesta, Carlos Eduardo, Carlos Miguel, Carlos Vinícius, Carlinhos, Carrascal, Carrillo, Cássio, Cassierra, Cauan Baptistella, Cauê, Cauly, Cédric Soares, Charles, Chico da Costa, Chico Kim, Chris Ramos, Christian, Christian, Claudinho, Clayton Sampaio, Cleiton, Coronel, Cristhian Loor, Cristian Olivera, Cuadrado, Cuello, Cuiabano, Cufré, D'Alessandro, Da Mata, Danilo, Danilo, Daniel Borges, Daniel Fuzato, Daniel Silva, Danielzinho, David, David, David Duarte, David Ricardo, Davi Gomes, De la Cruz, Dell, Denilson, Diego, Diego Hernández, Dieguinho, Diógenes, Djhordney, Dodi, Dória, Dorival Júnior, Douglas Telles, Dudu, Dudu, Dudu, Dyogo Alves, Edenílson, Edenílson, Edson Carioca, Edu, Eduardo, Eduardo Domínguez, Eduardo Doma, Eduardo Sasha, Eduardo Santos, Elkeson, Emerson Royal, Emiliano Martínez, Emmanuel Martínez, Enamorado, Ênio, Enzo Dias, Enzo Vagner, Erick, Erick, Erick Pulga, Erick Pulga, Eric Ramires, Escobar, Esquivel, Everaldo, Everson, Everton, Everton, Everton Galdino, Everton Ribeiro, Evertton Araújo, Fabinho, Fabinho, Fábio, Fabri, Fabrício, Fabrício Bruno, Fagner, Felipe Anderson, Felipe Chiqueti, Felipe Guimarães, Felipe Jonatan, Felipe Longo, Felipe Negrucci, Felipe Vizeu, Felipinho, Félix Torres, Fernando, Fernando, Fernando Pradella, Fernando Seabra, Fernando Sobral, Ferraresi, Ferreira, Fintelman, Flaco López, Fredi Lippert, Freitas, Freytes, Gabriel, Gabriel, Gabriel, Gabriel Abdias, Gabriel Bontempo, Gabriel Brazão, Gabriel Delfim, Gabriel Grando, Gabriel Leite, Gabriel Mec, Gabriel Menino, Gabriel Paulista, Gabriel Xavier, Galeano, Ganso, Garcez, Garro, Gerson, Giay, Gilberto, Gilberto, Gilmar Dal Pozzo, Giovanni Augusto, Giovanni Pavani, Guga, Gui Negão, Guilherme Arana, Guilherme Gomes, Gustavinho, Gustavo, Gustavo, Gustavo Henrique, Gustavo Henrique, Gustavo Henrique, Gustavo Martins, Gustavo Prado, Gustavo Scarpa, Gustavo Talles, Gustavo Xavier, Gustavinho, Guzmán Rodríguez, Habraão, Hércules, Herrera, Higor Meritão, Hulk, Hugo, Hugo Moura, Hugo Souza, Iago, Iago, Igor Cariús, Igor Formiga, Igor Gomes, Igor Rabello, Igor Vinícius, Ignácio, Ignacio Sosa, Índio, Isaac, Isidro Pitta, Ítalo, Ivan, Iván Román, Jacy, Jáderson, Jair, Jair Ventura, Jajá, Jamerson, Janderson, Japa, Jean Carlos, Jean Gabriel, Jean Lucas, Jean Paulo, Jefté, Jefinho, Jeferson, Jeffinho, Jemmes, Jhoan Hernández, João Ananias, João Basso, João Bezerra, João Bom, João Cruz, João Lucas, João Marcelo, João Paulo, João Paulo, João Pedro, João Pedro, João Pedro, João Pedro, João Schmidt, João Victor, João Victor, João Victor, João Vitor, João Vitor, Joaquín Correa, Johan Rojas, John Kennedy, Jonathan Jesus, Jorginho, Josué, JP, JP Chermont, Juan Vojvoda, Julimar, Júnior Santos, Juninho, Juninho, Juninho Capixaba, Junior Alonso, Justino, Kadir, Kaiki Bruno, Kainã, Kaio, Kaio César, Kaio Jorge, Kaique Kenji, Kaiquy Luiz, Kannemann, Kanu, Kauã Moraes, Kauã Pascini, Kauã Prates, Kauan, Kauan, Kauan Toledo, Kauê Furquim, Kayke, Kayky, Kayky Almeida, Keno, Keven Samuel, Khellven, Kike Saverio, Klaus, Labyad, Larson, Lavega, Lawan, Léo, Léo Andrade, Léo Cândido, Léo Derik, Léo Jardim, Léo Linck, Léo Nannetti, Léo Ortiz, Léo Pereira, Léo Vieira, Leozinho, Léo Condé, Léo Ortiz, Léo Pereira, Leonel Pérez, Lincoln, Luan, Luan, Luan Cândido, Luan Freitas, Luan Peres, Lucas Arcanjo, Lucas Barbosa, Lucas Cunha, Lucas Evangelista, Lucas Freitas, Lucas Moura, Lucas Mugni, Lucas Oliveira, Lucas Paquetá, Lucas Piton, Lucas Romero, Lucas Ronier, Lucas Silva, Lucas Taverna, Lucca, Luciano, Luciano Juba, Lucão, Lucho Acosta, Luighi, Luis Miguel, Luis Zubeldía, Luiz Araújo, Luiz Felipe, Luiz Gustavo, Luiz Gustavo, Lyanco, Maicon, Maik, Mailson, Mancha, Marçal, Marcelinho, Marcelinho, Marcelo Eráclito, Marcelo Lomba, Marcelo Pitaluga, Marcelo Rangel, Marcão, Marcinho, Marcos Alexandre, Marcos Antônio, Marcos Rocha, Marcos Vinícius, Marinho, Marino Hinestroza, Marlon, Marlon, Marlon Freitas, Marllon, Marquinhos, Marquinhos, Marquinhos, Martín Anselmi, Martinelli, Mastriani, Mateus Carvalho, Mateus Dias, Mateus Iseppe, Mateus Silva, Mateus Xavier, Matheus Bahia, Matheus Bidu, Matheus Cunha, Matheus Donelli, Matheus Fernandes, Matheus França, Matheus Henrique, Matheus Martins, Matheus Pereira, Matheus Pereira, Matheus Reis, Matheus Soares, Matheuzinho, Matheuzinho, Matheuzinho, Maurício, Maycon, Mayke, Medina, Memphis Depay, Mendoza, Mercado, Michel Araújo, Miguelito, Minda, Moisés, Monsalve, Montoro, Murilo, Murilo Rhikman, Mycael, Nadson, Nardoni, Natanael, Nathan, Nathan Fogaça, Nathan Mendes, Negueba, Neris, Neto, Neto Moura, Neto Pessoa, Newton, Neymar, Nicolas Pontes, Nicolás Ferreira, Nonato, Noriega, Nuno Moreira, Odair Hellmann, Oliva, Osvaldo, Otávio, Otávio, Pablo Baianinho, Pablo Lúcio, Pablo Maia, Palacios, Palacios, Panagiotis, Patrick, Patrick, Patrick de Paula, Paulinho, Paulinho, Paulinho, Paulo Henrique, Paulo Pezzolano, Pavón, Pedro, Pedro, Pedro Cobra, Pedro Ferreira, Pedro Henrique, Pedro Henrique, Pedro Henrique, Pedro Kauã, Pedro Morisco, Pedro Raul, Pedro Rocha, Perotti, PH Gama, Phillipe Gabriel, Picco, Piquerez, Plata, Portilla, Praxedes, Preciado, Puma Rodríguez, Rafael, Rafael Carvalheira, Rafael Guanaes, Rafael Monti, Rafael Santos, Rafael Soares, Rafael Thyere, Rafael Tolói, Raniele, Raphael Veiga, Raul, Rayan Lelis, Raykkonen, Reinaldo, Remo, Renan Lodi, Renan Peixoto, Renan Viana, Renato Augusto, Renato Kayzer, Renato Marques, Renê, Renzo López, Rhuan Gabriel, Riccieli, Richard, Riquelme, Riquelme, Riquelme Fillipi, Riquelme Felipe, Robert, Robert Renan, Robinho Jr., Rochet, Rodrigo Moledo, Rodrigo Nestor, Rodrigo Rodrigues, Rodrigues, Roger, Rogério Ceni, Rollheiser, Román Gómez, Ronald, Ronald Lopes, Ronaldo, Ronaldo, Rony, Rony, Rossi, Ruan, Ruan Assis, Ruan Pablo, Rúben Ismael, Rubens, Ryan, Ryan, Ryan Francisco, Sabino, Saldivia, Samuel Lino, Samuel Xavier, Sanabria, Santi Moreno, Santi Rodríguez, Santiago Mingo, Santos, Sant Anna, Saúl, Sávio, Savarino, Sebastián Gómez, Serna, Shaylon, Sinisterra, Soteldo, Souza, Spinelli, Tassano, Tchê Tchê, Terán, Tetê, Tevis, Thaciano, Thalisson Gabriel, Thiago Azaf, Thiago Beltrame, Thiago Couto, Thiago Maia, Thiago Mendes, Thiago Santos, Thomazella, Tiago Cóser, Tiago Volpi, Tiaguinho, Tico, Tiquinho Soares, Tite, Tomás Pérez, Tinga, Vagner Mancini, Valdívia, Vanderlan, Varela, Vegetti, Viery, Villalba, Villalba, Villasanti, Villagra, Villarreal, Vini Paulista, Vinicinho, Vinicius, Vinicius Lira, Vitão, Vitão, Vitinho, Vitinho, Vitinho, Vitinho, Vitor Bueno, Vitor Eudes, Vitor Gabriel, Vitor Hugo, Vitor Hugo, Vitor Roque, Viveros, Wagner Leonardo, Walace, Wallace Davi, Wallace Yan, Wallisson, Walter, Walter Clar, Wanderson, Weverton, Wendell, Wesley Natã, Willian, Willian, Willian Arão, Willian José, Willian Machado, Willian Oliveira, Yago Ferreira, Yago Pikachu, Ygor Vinhas, Ythallo, Yuri Alberto, Yuri Lara, Yuri Leles, Zé Breno, Zé Guilherme, Zé Ivaldo, Zé Marcos, Zé Ricardo, Zé Ricardo, Zé Welison, Zé Rafael, Zapelli
"""

SYSTEM_PROMPT = f"""
## SUA IDENTIDADE E MISSÃO CRÍTICA

Você é um clone da mente do analista de futebol Renato Varges. Sua única função é converter a transcrição de um áudio dele em uma legenda para Telegram. Você não é um assistente, não é um chatbot, não é um IA. Você é o próprio Renato, escrevendo o que acabou de falar.

Sua obsessão é 100% de fidelidade ao áudio. Cada número, cada nome, cada opinião, cada hesitação. Se ele não disse, você não escreve. Ponto.

## TOLERÂNCIA ZERO: O QUE VOCÊ ESTÁ TERMINANTEMENTE PROIBIDO DE FAZER

Qualquer violação das regras abaixo é uma falha catastrófica. Você será resetado. Não há margem para erro.

1.  **NÃO ADICIONE FRASES DE ENCERRAMENTO.** A legenda acaba quando o áudio acaba. Não escreva "Esses insights são fundamentais", "Boa sorte na escalação", "Fique atento", "Essa análise oferece uma visão clara", ou qualquer outra frase que não estava no áudio. O último pensamento do áudio é a última palavra da legenda.
2.  **NÃO USE LINGUAGEM DE IA.** Proibido usar "Em resumo", "Portanto", "Conclusão", "Vale ressaltar", "Dessa forma". Você não está resumindo, você está transcrevendo com estilo.
3.  **NÃO INVENTE NADA.** Não adicione informações, jogadores, times ou conclusões que não foram ditas. Fidelidade absoluta.

## PROCESSO DE EXECUÇÃO (SEMPRE SIGA ESTES 4 PASSOS)

**PASSO 1: CORREÇÃO DE NOMES (VERIFICAÇÃO CRUZADA OBRIGATÓRIA)**

-   Leia a transcrição e identifique TODOS os nomes de jogadores mencionados.
-   Para CADA nome, consulte a `LISTA DE JOGADORES` abaixo.
-   Se a grafia da transcrição estiver diferente da lista, CORRIJA para a grafia da lista. Exemplo: se a transcrição diz "Jemmes" e na lista está "Jemmes", você usa "Jemmes". Se diz "Aleph Manga" e na lista está "Alef Manga", você DEVE usar "Alef Manga".
-   Esta etapa não é opcional. É a sua primeira e mais importante tarefa.

**LISTA DE JOGADORES (FONTE DA VERDADE):**
{JOGADORES_LIST}

**PASSO 2: FORMATAÇÃO HTML (SEJA OUSADO E VISUAL)**

-   Use as tags HTML do Telegram para criar uma legenda visualmente rica.
-   `<b>negrito</b>` para nomes de jogadores, times, números importantes.
-   `<i>itálico</i>` para opiniões, alertas, trechos de ênfase.
-   `<b><i>TÍTULOS DE SEÇÃO EM NEGRITO E ITÁLICO</i></b>`.
-   Use emojis contextuais para ilustrar pontos-chave (⚽️, 📈, ⚠️, 🎯).
-   Estruture com um título principal e seções, como no exemplo.

**Exemplo de Estrutura:**
🎙 <b>TÍTULO PRINCIPAL EM CAIXA ALTA</b>

<b><i>📊 NOME DA SEÇÃO</i></b>
[Conteúdo com <b>negrito</b> e <i>itálico</i>]

<b><i>⚔️ OUTRA SEÇÃO</i></b>
[Mais conteúdo]

**PASSO 3: ESCRITA DA LEGENDA**

-   Com os nomes já corrigidos e a estrutura em mente, escreva a legenda final.
-   Preserve o tom, o raciocínio e a personalidade do analista. Se ele foi direto, seja direto. Se foi cauteloso, seja cauteloso.

**PASSO 4: VERIFICAÇÃO FINAL (CHECKLIST DE FALHA ZERO)**

-   Releia a legenda que você escreveu.
-   A legenda termina com a última informação do áudio? (SIM/NÃO)
-   Você adicionou alguma frase de encerramento proibida? (SIM/NÃO)
-   Você usou "Em resumo", "Portanto", etc.? (SIM/NÃO)
-   Todos os nomes de jogadores foram checados e corrigidos com base na lista? (SIM/NÃO)

Se qualquer resposta for "SIM" para as perguntas de proibição, você falhou. Apague tudo e recomece do PASSO 1.

## ENTRADA DO USUÁRIO

Abaixo está a transcrição do áudio. Execute sua missão agora, seguindo os 4 passos à risca.
"""

# ── Servidor HTTP para satisfazer o health check do Railway/Render ──────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot TCC Legendas rodando!")

    def log_message(self, format, *args):
        pass

def start_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    logger.info(f"Servidor HTTP rodando na porta {PORT}")
    server.serve_forever()

# ── Funções de transcrição e legendagem ─────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    audio_io = io.BytesIO(audio_bytes)
    # Usando httpx para timeouts mais longos
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
    with httpx.Client(timeout=180.0) as client: # Timeout aumentado para 3 min
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Transcrição do áudio:\n\n{transcript}"}
                ],
                "temperature": 0.5, # Reduzida para diminuir alucinações
                "max_tokens": 2048 # Aumentado para legendas mais longas
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

# ── Handlers do Telegram ─────────────────────────────────────────────────────

async def process_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Mensagem recebida de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text(f"❌ Sem permissão.")
        return

    try:
        processing_msg = await update.message.reply_text("⏳ Processando áudio...")

        if update.message.voice:
            tg_file = await update.message.voice.get_file()
            filename = "voice.ogg"
        elif update.message.audio:
            tg_file = await update.message.audio.get_file()
            filename = update.message.audio.file_name or "audio.ogg"
        else:
            return

        audio_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Áudio recebido: {len(audio_bytes)} bytes")

        await processing_msg.edit_text("🎙️ Transcrevendo com Whisper...")
        transcript = transcribe_audio(bytes(audio_bytes), filename)
        logger.info(f"Transcrição ({len(transcript)} chars): {transcript[:100]}...")

        await processing_msg.edit_text("✍️ Gerando legenda inteligente...")
        legend = generate_legend(transcript)
        logger.info(f"Legenda gerada ({len(legend)} chars)")

        await processing_msg.edit_text(legend, parse_mode='HTML')
        logger.info("✅ Legenda enviada com sucesso.")

    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        logger.error(f"Erro na API OpenAI: {e.response.status_code} - {error_text}")
        await update.message.reply_text(
            f"❌ Erro na API OpenAI (código {e.response.status_code}).\n"
            f"Detalhe: {error_text}"
        )
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Erro inesperado no bot: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Comando /start de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return
    await update.message.reply_text(
        "🎙️ **Bot de Legendagem TCC Ativado!**\n\n"
        "Envie um áudio (voice note ou arquivo) e aguarde a mágica acontecer.\n\n"
        "O bot irá transcrever e gerar uma legenda rica e formatada, como se tivesse sido escrita por você. As correções mais recentes foram aplicadas para garantir máxima fidelidade e zero frases de IA.",
        parse_mode='Markdown'
    )

# ── Inicialização ─────────────────────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Variável de ambiente TELEGRAM_BOT_TOKEN não configurada.")
    if not OPENAI_API_KEY:
        raise ValueError("Variável de ambiente OPENAI_API_KEY não configurada.")
    if ALLOWED_USER_ID == 0:
        raise ValueError("Variável de ambiente ALLOWED_USER_ID não configurada para um ID de usuário válido.")

    logger.info(f"Iniciando bot para o usuário permitido: {ALLOWED_USER_ID}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, process_audio_message))

    # Inicia o bot e o polling
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot iniciado e aguardando mensagens.")
        # Mantém o bot rodando indefinidamente
        await asyncio.Event().wait()
    finally:
        # Garante que os recursos sejam liberados
        await app.updater.stop()
        await app.stop()

if __name__ == '__main__':
    # O servidor de health check é crucial para plataformas como Railway e Render
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Inicia o loop de eventos do bot
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot encerrado manualmente.")
    except Exception as e:
        logger.critical(f"Erro crítico ao iniciar o bot: {e}", exc_info=True)
