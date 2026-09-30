"""
Robô do índice do canal: a cada rodada, monta um índice clicável dos blocos de conteúdo.

- O primeiro post de cada bloco leva a marca #TCC na legenda ("#TCC SEMÁFORO PREMIUM").
  O texto depois da marca vira o nome do item; sem texto, vale a primeira linha da legenda.
- Posts antigos entram editando a legenda para incluir a marca, ou com /adicionar LINK NOME.
- Os comandos ficam na conversa privada com o robô, longe da audiência do canal.
- /publicar sempre posta um índice NOVO no canal, com todos os itens da rodada até ali,
  para o índice atualizado aparecer lá embaixo, onde as pessoas estão lendo.
- A lista da rodada fica numa mensagem fixada na conversa privada: o disco do Render grátis
  é apagado a cada deploy, e o Telegram guarda essa mensagem para sempre.
"""

import html
import logging
import re
from dataclasses import dataclass, field

from telegram import LinkPreviewOptions, Message, MessageEntity, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

INDEX_MARKER_PATTERN = re.compile(r'#tcc(?!\w)', re.IGNORECASE)
YOUTUBE_PATTERN = re.compile(r'youtube\.com|youtu\.be', re.IGNORECASE)
PRIVATE_LINK_PATTERN = re.compile(r'^https?://t\.me/c/(\d+)/(?:\d+/)?(\d+)', re.IGNORECASE)
PUBLIC_LINK_PATTERN = re.compile(r'^https?://t\.me/([A-Za-z][A-Za-z0-9_]{3,})/(\d+)', re.IGNORECASE)
MEMORY_HEADER = "🗂 MEMÓRIA DO ÍNDICE (não desafixe esta mensagem)"
MEMORY_ITEM_PATTERN = re.compile(r'^(\d+) (-|yt) (.+)$')
MAX_TITLE_CHARS = 60
# a mensagem fixada que guarda a rodada tem o limite normal de texto do Telegram
MAX_MEMORY_CHARS = 4000

HELP_TEXT = (
    "<b>ROBÔ DO ÍNDICE</b>\n\n"
    "<b>Marcar um bloco:</b> no primeiro post do bloco, coloque na legenda\n"
    "<code>#TCC SEMÁFORO PREMIUM</code>\n"
    "Só <code>#TCC</code> também funciona: o nome vira a primeira linha da legenda.\n"
    "Post antigo? Edite a legenda e acrescente a marca.\n\n"
    "<b>Comandos:</b>\n"
    "/nova_rodada 28 — zera a lista e começa a rodada 28\n"
    "/indice — mostra como está o índice, com a numeração dos itens\n"
    "/publicar — posta e fixa o índice atualizado no canal (desafixa o anterior)\n"
    "/adicionar LINK NOME — inclui um post pelo link\n"
    "/remover 3 — tira o item 3\n"
    "/renomear 3 NOVO NOME — troca o nome do item 3\n"
    "/emoji_youtube [emoji] — troca o emoji dos itens do YouTube (premium ou comum)\n\n"
    "Post com link do YouTube (ou nome começando com ▶️) ganha o ícone do YouTube no índice."
)


@dataclass
class IndexItem:
    message_id: int
    title: str
    youtube: bool = False


@dataclass
class IndexState:
    rodada: str = ""
    channel_id: int | None = None
    channel_username: str | None = None
    items: dict[int, IndexItem] = field(default_factory=dict)
    youtube_emoji_id: str | None = None
    youtube_emoji_fallback: str = "▶️"
    # último índice fixado pelo robô: é desafixado quando sai o próximo
    last_index_message_id: int | None = None
    memory_message_id: int | None = None

    def sorted_items(self) -> list[IndexItem]:
        # sempre na ordem de publicação no canal, não na ordem em que foram marcados
        return [self.items[message_id] for message_id in sorted(self.items)]


# ── Texto: nome do item, links, índice e memória ─────────────────────────────

def clean_title(text: str) -> str:
    text = re.sub(r'\s+', ' ', text or '').strip(' -–—:|•')
    if len(text) > MAX_TITLE_CHARS:
        text = text[:MAX_TITLE_CHARS].rsplit(' ', 1)[0] + '…'
    return text.upper()


def split_youtube_flag(title: str) -> tuple[str, bool]:
    """"▶️ LIVE 1" -> ("LIVE 1", True): o ícone de vídeo sai do nome e vira o marcador."""
    stripped = title.lstrip()
    if stripped.startswith('▶'):
        return stripped.lstrip('▶️ ').strip(), True
    return title, False


def title_from_post(text: str) -> str:
    """Nome do item: o texto depois de #TCC ou, sem ele, a primeira linha da legenda."""
    lines = (text or '').splitlines()
    for line in lines:
        marker = INDEX_MARKER_PATTERN.search(line)
        if marker:
            title = clean_title(line[marker.end():])
            if title:
                return title
            break
    for line in lines:
        title = clean_title(INDEX_MARKER_PATTERN.sub('', line))
        if title:
            return title
    return 'CONTEÚDO'


def message_urls(message: Message) -> list[str]:
    entities = list(message.entities or ()) + list(message.caption_entities or ())
    return [entity.url for entity in entities if entity.url]


def post_link(state: IndexState, message_id: int) -> str:
    if state.channel_username:
        return f"https://t.me/{state.channel_username}/{message_id}"
    internal_id = str(state.channel_id or '')
    if internal_id.startswith('-100'):
        internal_id = internal_id[4:]
    return f"https://t.me/c/{internal_id}/{message_id}"


def youtube_marker(state: IndexState, *, premium: bool = True) -> str:
    if premium and state.youtube_emoji_id:
        return (f'<tg-emoji emoji-id="{state.youtube_emoji_id}">'
                f'{html.escape(state.youtube_emoji_fallback)}</tg-emoji>')
    # emoji comum escolhido pelo dono, ou o equivalente comum do premium recusado
    return html.escape(state.youtube_emoji_fallback or "▶️")


def render_index(state: IndexState, *, numbered: bool = False, premium: bool = True) -> str:
    title = f"ÍNDICE RODADA {state.rodada}" if state.rodada else "ÍNDICE"
    lines = [f"<b><i>{html.escape(title)}</i></b>", ""]
    for position, item in enumerate(state.sorted_items(), start=1):
        if numbered:
            marker = f"{position}."
        else:
            marker = youtube_marker(state, premium=premium) if item.youtube else "-"
        link = html.escape(post_link(state, item.message_id))
        # padrão do canal: nome do bloco em negrito e CAIXA ALTA
        lines.append(f'{marker} <a href="{link}"><b>{html.escape(item.title)}</b></a>')
    return "\n".join(lines)


def render_memory(state: IndexState) -> str:
    lines = [
        MEMORY_HEADER,
        f"rodada: {state.rodada}",
        f"canal: {state.channel_id or ''} {state.channel_username or '-'}",
        f"youtube: {state.youtube_emoji_id or '-'} {state.youtube_emoji_fallback}",
        f"ultimo_indice: {state.last_index_message_id or '-'}",
        "---",
    ]
    for item in state.sorted_items():
        lines.append(f"{item.message_id} {'yt' if item.youtube else '-'} {item.title}")
    return "\n".join(lines)


def parse_memory(text: str) -> IndexState:
    state = IndexState()
    for line in (text or '').splitlines()[1:]:
        if line.startswith('rodada:'):
            state.rodada = line.split(':', 1)[1].strip()
        elif line.startswith('canal:'):
            parts = line.split(':', 1)[1].split()
            if parts and re.fullmatch(r'-?\d+', parts[0]):
                state.channel_id = int(parts[0])
            if len(parts) > 1 and parts[1] != '-':
                state.channel_username = parts[1]
        elif line.startswith('ultimo_indice:'):
            value = line.split(':', 1)[1].strip()
            if value.isdigit():
                state.last_index_message_id = int(value)
        elif line.startswith('youtube:'):
            parts = line.split(':', 1)[1].split()
            if parts and parts[0].isdigit():
                state.youtube_emoji_id = parts[0]
            if len(parts) > 1:
                state.youtube_emoji_fallback = parts[1]
        else:
            match = MEMORY_ITEM_PATTERN.match(line)
            if match:
                message_id = int(match.group(1))
                state.items[message_id] = IndexItem(message_id, match.group(3), match.group(2) == 'yt')
    return state


# ── Memória fixada na conversa privada ───────────────────────────────────────

async def load_state(bot, owner_id: int) -> IndexState:
    try:
        chat = await bot.get_chat(owner_id)
    except TelegramError as exc:
        logger.warning("Índice: não li a memória fixada (o dono já deu /start no robô?): %s", exc)
        return IndexState()

    pinned = chat.pinned_message
    if not pinned or not (pinned.text or '').startswith(MEMORY_HEADER):
        logger.info("Índice: nenhuma memória fixada; começando vazio.")
        return IndexState()

    state = parse_memory(pinned.text)
    state.memory_message_id = pinned.message_id
    logger.info("Índice: rodada %s carregada com %s itens.", state.rodada or '-', len(state.items))
    return state


async def save_state(bot, owner_id: int, state: IndexState) -> None:
    text = render_memory(state)
    if len(text) > MAX_MEMORY_CHARS:
        raise ValueError("a lista da rodada passou do tamanho que cabe na memória fixada")

    if state.memory_message_id:
        try:
            await bot.edit_message_text(chat_id=owner_id, message_id=state.memory_message_id, text=text)
            return
        except BadRequest as exc:
            if 'not modified' in str(exc).lower():
                return
            logger.warning("Índice: memória fixada sumiu, criando outra: %s", exc)

    memory = await bot.send_message(owner_id, text, disable_notification=True)
    await bot.pin_chat_message(owner_id, memory.message_id, disable_notification=True)
    state.memory_message_id = memory.message_id


# ── Handlers ─────────────────────────────────────────────────────────────────

def _state(context: ContextTypes.DEFAULT_TYPE) -> IndexState:
    return context.bot_data['index_state']


def _owner(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.bot_data['owner_id']


async def _save_and_report(context: ContextTypes.DEFAULT_TYPE, note: str) -> None:
    owner_id = _owner(context)
    try:
        await save_state(context.bot, owner_id, _state(context))
    except (TelegramError, ValueError) as exc:
        logger.error("Índice: falha ao salvar a memória: %s", exc)
        note += f"\n\n⚠️ Não consegui salvar a lista ({html.escape(str(exc))}). Ela vale até o próximo reinício."
    try:
        await context.bot.send_message(owner_id, note, parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        logger.warning("Índice: não consegui avisar o dono (ele já deu /start no robô?): %s", exc)


async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post novo ou editado no canal: entra no índice se tiver #TCC, sai se a marca for tirada."""
    message = update.effective_message
    if message is None:
        return
    state = _state(context)
    if state.channel_id is not None and message.chat.id != state.channel_id:
        return

    text = message.text or message.caption or ''
    existing = state.items.get(message.message_id)
    if not INDEX_MARKER_PATTERN.search(text):
        if existing and update.edited_channel_post is not None:
            del state.items[message.message_id]
            await _save_and_report(context, f"➖ <b>{html.escape(existing.title)}</b> saiu do índice.")
        return

    if state.channel_id is None:
        state.channel_id = message.chat.id
    state.channel_username = message.chat.username

    title, marked_as_video = split_youtube_flag(title_from_post(text))
    youtube = (marked_as_video or bool(YOUTUBE_PATTERN.search(text))
               or any(YOUTUBE_PATTERN.search(url) for url in message_urls(message)))
    if existing and existing.title == title and existing.youtube == youtube:
        return      # edição em outra parte do post: nada muda no índice

    state.items[message.message_id] = IndexItem(message.message_id, title, youtube)
    position = [item.message_id for item in state.sorted_items()].index(message.message_id) + 1
    verb = "foi atualizado" if existing else "entrou no índice"
    note = f"✅ <b>{html.escape(title)}</b> {verb} (item {position} de {len(state.items)})."
    if not state.rodada:
        note += "\n\nDica: use /nova_rodada com o número da rodada para o título do índice."
    await _save_and_report(context, note)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_nova_rodada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Diga o número da rodada: /nova_rodada 28")
        return
    state = _state(context)
    anterior, total = state.rodada, len(state.items)
    state.rodada = " ".join(context.args).strip().upper()
    state.items.clear()
    note = f"🆕 <b>Rodada {html.escape(state.rodada)}</b> iniciada, com o índice vazio."
    if total:
        note += (f"\nA lista da rodada {html.escape(anterior or '-')} ({total} itens) foi zerada; "
                 "os índices já publicados continuam no canal.")
    await _save_and_report(context, note)


async def cmd_indice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    if not state.items:
        await update.effective_message.reply_text(
            "O índice está vazio. Marque o primeiro post de cada bloco com #TCC.")
        return
    await update.effective_message.reply_text(
        render_index(state, numbered=True) + "\n\n<i>Números para usar em /remover e /renomear.</i>",
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def _send_index(context: ContextTypes.DEFAULT_TYPE, state: IndexState, *, premium: bool) -> Message:
    return await context.bot.send_message(
        state.channel_id,
        render_index(state, premium=premium),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def cmd_emoji_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Troca o emoji dos itens do YouTube. O comando vem junto com o emoji, premium ou comum."""
    message = update.effective_message
    state = _state(context)
    emojis = message.parse_entities([MessageEntity.CUSTOM_EMOJI])
    if emojis:
        entity, fallback = next(iter(emojis.items()))
        state.youtube_emoji_id = entity.custom_emoji_id
        state.youtube_emoji_fallback = fallback or "▶️"
    elif context.args:
        state.youtube_emoji_id = None
        state.youtube_emoji_fallback = context.args[0]
    else:
        await message.reply_text(
            "Mande o comando junto com o emoji, na mesma mensagem (premium ou comum):\n"
            "/emoji_youtube 🔴")
        return
    await _save_and_report(
        context,
        f'✅ Emoji do YouTube cadastrado: {youtube_marker(state)} — ele marca os itens com link do YouTube.')


async def _pin_new_index(context: ContextTypes.DEFAULT_TYPE, state: IndexState, message_id: int) -> str:
    """Fixa o índice recém-publicado e desafixa o anterior. Devolve um aviso se não conseguir."""
    try:
        # o post do índice já notifica a audiência; fixar não precisa notificar de novo
        await context.bot.pin_chat_message(state.channel_id, message_id, disable_notification=True)
    except TelegramError as exc:
        logger.warning("Índice: não consegui fixar o índice no canal: %s", exc)
        return ("\n\n📌 Não consegui fixar o índice. Para o robô fixar sozinho, dê a ele a permissão "
                "<b>Editar mensagens de outros</b> em Administradores do canal.")

    anterior, state.last_index_message_id = state.last_index_message_id, message_id
    if anterior and anterior != message_id:
        try:
            await context.bot.unpin_chat_message(state.channel_id, message_id=anterior)
        except TelegramError as exc:
            logger.warning("Índice: não consegui desafixar o índice anterior: %s", exc)
    try:
        await save_state(context.bot, _owner(context), state)
    except (TelegramError, ValueError) as exc:
        logger.error("Índice: falha ao salvar a memória: %s", exc)
    return ""


async def cmd_publicar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    if not state.items:
        await update.effective_message.reply_text("Não há nada para publicar: o índice está vazio.")
        return
    if state.channel_id is None:
        await update.effective_message.reply_text(
            "Ainda não sei qual é o canal. Marque um post com #TCC ou use /adicionar com um link.")
        return

    aviso = ""
    try:
        try:
            published = await _send_index(context, state, premium=True)
        except BadRequest as exc:
            if not state.youtube_emoji_id:
                raise
            # o Telegram pode não deixar robô usar emoji premium no canal: publica com o comum
            logger.warning("Índice: emoji premium recusado no canal, usando o comum: %s", exc)
            published = await _send_index(context, state, premium=False)
            aviso = ("\n\n⚠️ O Telegram não deixou o robô usar o emoji premium do YouTube no canal; "
                     f"saiu {youtube_marker(state, premium=False)} no lugar.")
    except TelegramError as exc:
        logger.error("Índice: falha ao publicar no canal: %s", exc)
        await update.effective_message.reply_text(
            f"❌ Não consegui publicar no canal: {exc}\n"
            "Confira se o robô é administrador do canal com permissão para publicar.")
        return

    aviso += await _pin_new_index(context, state, published.message_id)
    fixado = " e fixado" if state.last_index_message_id == published.message_id else ""
    link = html.escape(post_link(state, published.message_id))
    await update.effective_message.reply_text(
        f'✅ <a href="{link}">Índice publicado</a>{fixado} no canal com {len(state.items)} itens.{aviso}',
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def cmd_adicionar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inclui um post antigo pelo link. O robô não lê posts antigos, então o nome vem junto."""
    uso = "Use assim: /adicionar https://t.me/c/123/456 SEMÁFORO PREMIUM"
    if len(context.args) < 2:
        await update.effective_message.reply_text(f"Faltou o link ou o nome. {uso}")
        return

    link, nome = context.args[0], " ".join(context.args[1:])
    state = _state(context)
    private = PRIVATE_LINK_PATTERN.match(link)
    public = PUBLIC_LINK_PATTERN.match(link)
    if private:
        channel_id, username, message_id = int(f"-100{private.group(1)}"), None, int(private.group(2))
    elif public:
        username, message_id = public.group(1), int(public.group(2))
        try:
            channel_id = (await context.bot.get_chat(f"@{username}")).id
        except TelegramError:
            await update.effective_message.reply_text(
                "Não encontrei esse canal. Confira o link e se o robô é administrador dele.")
            return
    else:
        await update.effective_message.reply_text(f"Não reconheci o link. {uso}")
        return

    if state.channel_id is not None and channel_id != state.channel_id:
        await update.effective_message.reply_text("Esse link é de outro canal; não entrou no índice.")
        return
    if state.channel_id is None:
        state.channel_id = channel_id
    if username:
        state.channel_username = username

    title, youtube = split_youtube_flag(nome)
    title = clean_title(title)
    existing = state.items.get(message_id)
    state.items[message_id] = IndexItem(message_id, title, youtube)
    position = [item.message_id for item in state.sorted_items()].index(message_id) + 1
    verb = "foi atualizado" if existing else "entrou no índice"
    await _save_and_report(
        context, f"✅ <b>{html.escape(title)}</b> {verb} (item {position} de {len(state.items)}).")


def _item_by_position(state: IndexState, raw: str) -> IndexItem | None:
    if not raw.isdigit():
        return None
    items = state.sorted_items()
    position = int(raw)
    return items[position - 1] if 1 <= position <= len(items) else None


async def cmd_remover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    item = _item_by_position(state, context.args[0]) if context.args else None
    if item is None:
        await update.effective_message.reply_text("Diga o número do item (veja em /indice): /remover 3")
        return
    del state.items[item.message_id]
    await _save_and_report(context, f"➖ <b>{html.escape(item.title)}</b> saiu do índice.")


async def cmd_renomear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    item = _item_by_position(state, context.args[0]) if context.args else None
    if item is None or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Diga o número do item e o novo nome (veja em /indice): /renomear 3 NOVO NOME")
        return
    antigo = item.title
    title, youtube = split_youtube_flag(" ".join(context.args[1:]))
    item.title = clean_title(title)
    item.youtube = youtube or item.youtube
    await _save_and_report(
        context, f"✏️ <b>{html.escape(antigo)}</b> agora é <b>{html.escape(item.title)}</b>.")


# ── Inicialização ────────────────────────────────────────────────────────────

async def start_index_bot(token: str, owner_id: int) -> Application:
    """Sobe o robô do índice no mesmo processo do robô de legendas."""
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(30.0)
        .build()
    )
    dono = filters.ChatType.PRIVATE & filters.User(user_id=owner_id)
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, on_channel_post))
    app.add_handler(CommandHandler(["start", "ajuda"], cmd_help, filters=dono))
    app.add_handler(CommandHandler("nova_rodada", cmd_nova_rodada, filters=dono))
    app.add_handler(CommandHandler("indice", cmd_indice, filters=dono))
    app.add_handler(CommandHandler("publicar", cmd_publicar, filters=dono))
    app.add_handler(CommandHandler("adicionar", cmd_adicionar, filters=dono))
    app.add_handler(CommandHandler("remover", cmd_remover, filters=dono))
    app.add_handler(CommandHandler("renomear", cmd_renomear, filters=dono))
    app.add_handler(CommandHandler("emoji_youtube", cmd_emoji_youtube, filters=dono))

    await app.initialize()
    logger.info("Robô do índice conectado como @%s.", app.bot.username)
    app.bot_data['owner_id'] = owner_id
    app.bot_data['index_state'] = await load_state(app.bot, owner_id)
    await app.start()
    # sem drop_pending_updates: posts marcados enquanto o servidor reiniciava não podem se perder
    await app.updater.start_polling(
        allowed_updates=["message", "channel_post", "edited_channel_post"],
    )
    logger.info("Robô do índice rodando.")
    return app
