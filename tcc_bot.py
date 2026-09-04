#!/usr/bin/env python3
"""
Bot Telegram - Transcrição e Legendagem de Áudios
Railway/Render compatible (HTTP health check included)
HTML parse_mode for Telegram formatting
"""

import os
import csv
import logging
import io
import asyncio
import threading
import time
import html
import re
import mimetypes
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.error import TimedOut
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# httpx loga a URL completa de cada requisicao, incluindo o token do bot na URL da API do Telegram.
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))
LEGACY_OPENAI_TEXT_MODEL = os.getenv('OPENAI_TEXT_MODEL')
OPENAI_TRANSCRIPTION_MODEL = os.getenv('OPENAI_TRANSCRIPTION_MODEL', 'gpt-transcribe')
OPENAI_NAMES_MODEL = os.getenv('OPENAI_NAMES_MODEL', LEGACY_OPENAI_TEXT_MODEL or 'gpt-5.6-terra')
OPENAI_CAPTION_MODEL = os.getenv('OPENAI_CAPTION_MODEL', LEGACY_OPENAI_TEXT_MODEL or 'gpt-5.6-sol')
OPENAI_AUDIO_SIZE_LIMIT_BYTES = 25 * 1024 * 1024
SUPPORTED_TRANSCRIPTION_EXTENSIONS = {
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".ogg",
    ".wav",
    ".webm",
}
AUDIO_MIME_BY_EXTENSION = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


class UserFacingError(Exception):
    """Erro com mensagem segura para exibir no Telegram."""


ALLOWED_TELEGRAM_TAGS = {"b", "i"}
ALLOWED_TELEGRAM_TAG_PATTERN = re.compile(r"</?(b|i)>", re.IGNORECASE)
CODE_FENCE_LINE_PATTERN = re.compile(r"^\s*```(?:html)?\s*$", re.IGNORECASE)
LANGUAGE_HINT_LINE_PATTERN = re.compile(r"^\s*html\s*$", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
TITLE_WITH_BOLD_PATTERN = re.compile(r"^(?P<before>.*?)(?:<b>(?P<title>.*?)</b>)(?P<after>.*)$", re.IGNORECASE)
TITLE_EMOJI_PATTERN = re.compile(
    r"(?:[\U0001F1E6-\U0001F1FF]{2}|[0-9#*]\ufe0f?\u20e3|"
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\ufe0f?)"
)
BULLET_LEADING_EMOJI_PATTERN = re.compile(
    r"(?m)^(?P<prefix>\s*-\s*)"
    r"(?:(?:[\U0001F1E6-\U0001F1FF]{2}|[0-9#*]\ufe0f?\u20e3|"
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\ufe0f?)\s*)+"
)
TITLE_EDGE_CLEANUP_PATTERN = re.compile(r"^[\s\-:;|\u2022\u2013\u2014]+|[\s\-:;|\u2022\u2013\u2014]+$")
DEFAULT_TITLE_EMOJI = "\U0001F4CC"
MAX_HEADING_EMOJIS = 3


@dataclass(frozen=True)
class LegendProfile:
    min_plain_chars: int
    max_plain_chars: int
    max_lines: int
    max_bullets: int
    generation_tokens: int
    compaction_tokens: int


def _get_retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def _extract_openai_error(response: httpx.Response) -> tuple[str, str | None, str | None]:
    fallback_message = response.text.strip()
    message = fallback_message
    error_type = None
    error_code = None

    try:
        payload = response.json()
    except ValueError:
        return message, error_type, error_code

    error = payload.get("error") or {}
    message = error.get("message") or fallback_message
    error_type = error.get("type")
    error_code = error.get("code")
    return message, error_type, error_code


def _openai_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


def _safe_audio_filename(filename: str | None, mime_type: str | None, default: str) -> str:
    filename = os.path.basename(filename or "").strip()

    if not filename:
        guessed_extension = mimetypes.guess_extension(mime_type or "") or os.path.splitext(default)[1]
        filename = f"audio{guessed_extension}"

    stem, extension = os.path.splitext(filename)
    extension = extension.lower()

    if extension == ".oga":
        extension = ".ogg"
    elif not extension:
        guessed_extension = mimetypes.guess_extension(mime_type or "") or os.path.splitext(default)[1]
        extension = ".ogg" if guessed_extension == ".oga" else guessed_extension.lower()

    if extension not in SUPPORTED_TRANSCRIPTION_EXTENSIONS:
        supported = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_TRANSCRIPTION_EXTENSIONS))
        raise UserFacingError(
            "❌ Formato de áudio não suportado pela transcrição. "
            f"Recebi `{extension or 'sem extensão'}`; envie em um destes formatos: {supported}."
        )

    safe_stem = stem or "audio"
    return f"{safe_stem}{extension}"


def _audio_mime_type(filename: str, telegram_mime_type: str | None = None) -> str:
    extension = os.path.splitext(filename)[1].lower()

    if telegram_mime_type and telegram_mime_type.startswith("audio/"):
        if telegram_mime_type in {"audio/oga", "audio/x-ogg"}:
            return "audio/ogg"
        return telegram_mime_type

    return AUDIO_MIME_BY_EXTENSION.get(extension) or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _ensure_audio_size_is_supported(size_bytes: int | None) -> None:
    if not size_bytes:
        return

    if size_bytes > OPENAI_AUDIO_SIZE_LIMIT_BYTES:
        size_mb = size_bytes / (1024 * 1024)
        raise UserFacingError(
            "❌ Esse áudio passou do limite de 25 MB da OpenAI "
            f"({size_mb:.1f} MB). Envie um áudio menor, comprimido ou dividido em partes."
        )


def get_transcription_timeout(duration_seconds: int | None) -> float:
    if not duration_seconds:
        return 300.0

    # Áudios longos podem levar vários minutos no endpoint de transcrição.
    return float(min(max(180, duration_seconds // 2 + 180), 900))


def get_legend_profile(transcript: str) -> LegendProfile:
    word_count = len((transcript or "").split())

    if word_count <= 140:
        return LegendProfile(
            min_plain_chars=260,
            max_plain_chars=760,
            max_lines=9,
            max_bullets=4,
            generation_tokens=420,
            compaction_tokens=320,
        )

    if word_count <= 350:
        return LegendProfile(
            min_plain_chars=380,
            max_plain_chars=1000,
            max_lines=11,
            max_bullets=5,
            generation_tokens=560,
            compaction_tokens=420,
        )

    if word_count <= 750:
        return LegendProfile(
            min_plain_chars=520,
            max_plain_chars=1250,
            max_lines=14,
            max_bullets=6,
            generation_tokens=760,
            compaction_tokens=560,
        )

    return LegendProfile(
        min_plain_chars=650,
        max_plain_chars=1450,
        max_lines=16,
        max_bullets=7,
        generation_tokens=960,
        compaction_tokens=720,
    )


def get_legend_budget_instruction(transcript: str) -> str:
    profile = get_legend_profile(transcript)
    return (
        "Orcamento da legenda: "
        f"{profile.min_plain_chars} a {profile.max_plain_chars} caracteres visiveis, "
        f"ate {profile.max_bullets} bullets e ate {profile.max_lines} linhas com texto. "
        "Use menos que isso se a fala for simples; use o limite superior so quando houver ideias centrais distintas."
    )


def get_name_correction_max_tokens(transcript: str) -> int:
    word_count = len((transcript or "").split())
    return min(max(int(word_count * 2.0) + 500, 1200), 4000)


def sanitize_telegram_html(text: str) -> str:
    """Mantém apenas <b> e <i>, escapando o restante e balanceando as tags."""
    if not text:
        return text

    parts = []
    stack: list[str] = []
    last_index = 0

    for match in ALLOWED_TELEGRAM_TAG_PATTERN.finditer(text):
        parts.append(html.escape(text[last_index:match.start()], quote=False))

        tag = match.group(1).lower()
        raw_tag = match.group(0)
        is_closing_tag = raw_tag.startswith("</")

        if is_closing_tag:
            if tag in stack:
                while stack:
                    open_tag = stack.pop()
                    parts.append(f"</{open_tag}>")
                    if open_tag == tag:
                        break
        else:
            parts.append(f"<{tag}>")
            stack.append(tag)

        last_index = match.end()

    parts.append(html.escape(text[last_index:], quote=False))

    while stack:
        parts.append(f"</{stack.pop()}>")

    return "".join(parts)


def strip_model_wrappers(text: str) -> str:
    if not text:
        return text

    lines = text.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    while lines and (
        CODE_FENCE_LINE_PATTERN.match(lines[0]) or LANGUAGE_HINT_LINE_PATTERN.match(lines[0])
    ):
        lines.pop(0)

    while lines and CODE_FENCE_LINE_PATTERN.match(lines[-1]):
        lines.pop()

    cleaned = "\n".join(lines).strip()
    cleaned = cleaned.replace("```html", "").replace("```HTML", "").replace("```", "")
    return cleaned.strip()


def _first_title_emoji(*parts: str) -> str:
    for part in parts:
        match = TITLE_EMOJI_PATTERN.search(part or "")
        if match:
            return match.group(0)
    return DEFAULT_TITLE_EMOJI


def _cleanup_title_text(text: str) -> str:
    text = html.unescape(_strip_html_tags(text or ""))
    text = TITLE_EMOJI_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = TITLE_EDGE_CLEANUP_PATTERN.sub("", text.strip())
    return text.strip()


def _looks_like_heading(text: str) -> bool:
    if not text or len(text) > 90:
        return False

    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False

    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return uppercase_ratio >= 0.65


def _normalize_heading_line(line: str, *, force: bool = False) -> str | None:
    stripped_line = line.strip()
    match = TITLE_WITH_BOLD_PATTERN.match(stripped_line)

    if match:
        before = match.group("before")
        title = match.group("title")
        after = match.group("after")
        outside_text = _cleanup_title_text(f"{before} {after}")
        title_text = _cleanup_title_text(title)

        if not force and outside_text:
            return None
        if not force and not TITLE_EMOJI_PATTERN.search(stripped_line) and not _looks_like_heading(title_text):
            return None

        emoji = _first_title_emoji(before, title, after)
        safe_title = html.escape((title_text or outside_text or "ANALISE").upper(), quote=False)
        return f"{emoji} <b>{safe_title}</b>"

    title_text = _cleanup_title_text(stripped_line)
    if not force and not _looks_like_heading(title_text):
        return None

    emoji = _first_title_emoji(stripped_line)
    safe_title = html.escape((title_text or "ANALISE").upper(), quote=False)
    return f"{emoji} <b>{safe_title}</b>"


def force_main_title_uppercase(text: str) -> str:
    if not text:
        return text

    lines = text.splitlines()
    normalized_first_heading = False
    heading_emoji_count = 0

    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if CODE_FENCE_LINE_PATTERN.match(stripped_line) or LANGUAGE_HINT_LINE_PATTERN.match(stripped_line):
            continue

        normalized = _normalize_heading_line(line, force=not normalized_first_heading)
        if normalized:
            heading_emoji_count += 1
            if heading_emoji_count > MAX_HEADING_EMOJIS:
                normalized = TITLE_EMOJI_PATTERN.sub("", normalized, count=1).lstrip()
            lines[index] = normalized
            normalized_first_heading = True

    return "\n".join(lines)


def reduce_excess_line_emojis(text: str) -> str:
    if not text:
        return text

    return BULLET_LEADING_EMOJI_PATTERN.sub(r"\g<prefix>", text)


def _strip_html_tags(text: str) -> str:
    return HTML_TAG_PATTERN.sub("", text or "")


def legend_needs_compaction(legend: str, transcript: str = "") -> bool:
    profile = get_legend_profile(transcript)
    plain_text = _strip_html_tags(legend)
    non_empty_lines = [line.strip() for line in plain_text.splitlines() if line.strip()]
    bullet_count = sum(1 for line in non_empty_lines if line.startswith("-"))

    return (
        len(plain_text) > profile.max_plain_chars
        or len(non_empty_lines) > profile.max_lines
        or bullet_count > profile.max_bullets
    )


def _extract_chat_completion_text(response: httpx.Response, action_name: str) -> tuple[str, str | None]:
    payload = response.json()
    choice = payload["choices"][0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = payload.get("usage") or {}

    logger.info(
        "%s concluído | finish_reason=%s prompt_tokens=%s completion_tokens=%s",
        action_name,
        finish_reason,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
    )

    return content, finish_reason


def _merge_with_overlap(base: str, addition: str) -> str:
    if not base:
        return addition
    if not addition:
        return base

    addition = addition.lstrip()
    max_overlap = min(len(base), len(addition), 200)

    for overlap in range(max_overlap, 19, -1):
        if base[-overlap:] == addition[:overlap]:
            return base + addition[overlap:]

    if addition and addition in base[-400:]:
        return base

    separator = " " if base[-1].isalnum() and addition[0].isalnum() else ""
    return base + separator + addition


def _is_reasoning_model(model: str) -> bool:
    """Modelos de raciocinio (familia GPT-5.x em diante) nao aceitam temperature/top_p
    via Chat Completions e usam max_completion_tokens em vez de max_tokens."""
    model = (model or "").lower()
    return not (model.startswith("gpt-4") or model.startswith("gpt-3"))


def _chat_completion_with_auto_continue(
    *,
    action_name: str,
    timeout: float,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    continue_instruction: str,
    max_rounds: int = 4,
) -> str:
    conversation = [dict(message) for message in messages]
    combined_text = ""
    reasoning_model = _is_reasoning_model(model)

    for round_index in range(1, max_rounds + 1):
        payload = {"model": model, "messages": conversation}
        if reasoning_model:
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens

        response = _post_openai(
            "https://api.openai.com/v1/chat/completions",
            timeout=timeout,
            action_name=action_name,
            json=payload,
        )
        chunk, finish_reason = _extract_chat_completion_text(response, action_name)
        combined_text = _merge_with_overlap(combined_text, chunk)

        if finish_reason != "length":
            return combined_text.strip()

        logger.warning(
            "%s foi cortado por limite de tokens na rodada %s. Pedindo continuação automática.",
            action_name,
            round_index,
        )

        conversation.extend([
            {"role": "assistant", "content": chunk},
            {"role": "user", "content": continue_instruction},
        ])

    logger.warning("%s ainda terminou cortado após %s rodadas.", action_name, max_rounds)
    return combined_text.strip()


def _post_openai(url: str, *, timeout: float, action_name: str, **kwargs) -> httpx.Response:
    max_attempts = 3

    with httpx.Client(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.post(url, headers=_openai_headers(), **kwargs)
            except httpx.RequestError as exc:
                if attempt < max_attempts:
                    delay = min(2 ** (attempt - 1), 8)
                    logger.warning(
                        "%s falhou por erro de rede/timeout (%s/%s). Nova tentativa em %.1fs. error=%s",
                        action_name,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    continue

                logger.error("%s falhou por erro de rede/timeout: %s", action_name, exc)
                raise UserFacingError(
                    "❌ Não consegui conectar à OpenAI agora. "
                    "Tente novamente em instantes."
                )

            if response.status_code < 400:
                return response

            message, error_type, error_code = _extract_openai_error(response)
            lower_message = (message or "").lower()

            if response.status_code == 429:
                if error_code == "insufficient_quota" or any(
                    term in lower_message for term in ("quota", "billing", "credit", "crédito", "saldo")
                ):
                    raise UserFacingError(
                        "❌ A conta da OpenAI está sem créditos ou sem billing ativo. "
                        "Confira saldo e faturamento no projeto da chave API."
                    )

                if attempt < max_attempts:
                    delay = _get_retry_delay(response, attempt)
                    logger.warning(
                        "%s recebeu 429 (%s/%s). Nova tentativa em %.1fs. type=%s code=%s message=%s",
                        action_name,
                        attempt,
                        max_attempts,
                        delay,
                        error_type,
                        error_code,
                        message,
                    )
                    time.sleep(delay)
                    continue

                raise UserFacingError(
                    "❌ A OpenAI limitou temporariamente as requisições. "
                    "Tente novamente em alguns segundos."
                )

            if response.status_code in {408, 409} or response.status_code >= 500:
                if attempt < max_attempts:
                    delay = _get_retry_delay(response, attempt)
                    logger.warning(
                        "%s recebeu erro temporário %s (%s/%s). Nova tentativa em %.1fs. type=%s code=%s message=%s",
                        action_name,
                        response.status_code,
                        attempt,
                        max_attempts,
                        delay,
                        error_type,
                        error_code,
                        message,
                    )
                    time.sleep(delay)
                    continue

                raise UserFacingError(
                    "❌ A OpenAI falhou temporariamente durante o processamento. "
                    "Tente reenviar o áudio em instantes."
                )

            if response.status_code == 401:
                raise UserFacingError(
                    "❌ A chave da OpenAI foi rejeitada. Verifique a variável OPENAI_API_KEY."
                )

            if response.status_code == 403:
                raise UserFacingError(
                    "❌ O projeto da OpenAI não tem permissão para esse modelo ou endpoint."
                )

            if response.status_code == 413:
                raise UserFacingError(
                    "❌ O áudio passou do limite de tamanho aceito pela OpenAI. "
                    "Envie um áudio menor, comprimido ou dividido em partes."
                )

            if response.status_code in {400, 404, 422}:
                if any(term in lower_message for term in ("audio", "file", "format", "formato")):
                    raise UserFacingError(
                        "❌ A OpenAI rejeitou o arquivo de áudio. "
                        "Tente reenviar como áudio do Telegram ou em MP3, M4A, WAV, OGG ou WEBM."
                    )

                if any(term in lower_message for term in ("model", "modelo")):
                    raise UserFacingError(
                        "❌ A OpenAI rejeitou o modelo configurado. "
                        "Verifique OPENAI_TRANSCRIPTION_MODEL, OPENAI_NAMES_MODEL e OPENAI_CAPTION_MODEL."
                    )

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Erro OpenAI em %s: status=%s type=%s code=%s message=%s",
                    action_name,
                    response.status_code,
                    error_type,
                    error_code,
                    message,
                )
                raise exc

    raise RuntimeError(f"Falha inesperada ao executar {action_name}")


# Mapa de abreviacao -> nome de exibicao dos times da Serie A. A API do Cartola
# so devolve a abreviacao (ex: "CAP"), entao mantemos o nome completo aqui.
CARTOLA_TEAM_NAMES = {
    'BAH': 'Bahia', 'BOT': 'Botafogo', 'CAM': 'Atlético-MG', 'CAP': 'Athlético-PR',
    'CFC': 'Coritiba', 'CHA': 'Chapecoense', 'COR': 'Corinthians', 'CRU': 'Cruzeiro',
    'FLA': 'Flamengo', 'FLU': 'Fluminense', 'GRE': 'Grêmio', 'INT': 'Internacional',
    'MIR': 'Mirassol', 'PAL': 'Palmeiras', 'RBB': 'Bragantino', 'REM': 'Remo',
    'SAN': 'Santos', 'SAO': 'São Paulo', 'VAS': 'Vasco', 'VIT': 'Vitória',
}


def _build_reference_strings(player_rows):
    """player_rows: iteravel de (apelido, nome, time).
    Retorna (referencia, whisper_names, times_ref, total_jogadores, total_times).
    """
    ref_lines = []
    whisper_names = []
    teams_dict = {}
    seen = set()
    for apelido, nome, time in player_rows:
        apelido = (apelido or "").strip()
        nome = (nome or "").strip()
        time = (time or "").strip()
        if not apelido or not time:
            continue
        if apelido not in seen:
            seen.add(apelido)
            ref_lines.append(f"{apelido} ({time}): {nome}")
            whisper_names.append(apelido)
        teams_dict.setdefault(time, [])
        if apelido not in teams_dict[time]:
            teams_dict[time].append(apelido)

    team_ref_lines = [f"{t}: {', '.join(p)}" for t, p in sorted(teams_dict.items())]
    return (
        "\n".join(ref_lines),
        ", ".join(whisper_names[:120]),
        "\n".join(team_ref_lines),
        len(ref_lines),
        len(teams_dict),
    )


def _fetch_players_from_cartola_api(timeout: float = 10.0):
    """Busca o elenco atual direto da API publica do Cartola FC. Levanta excecao se falhar."""
    with httpx.Client(timeout=timeout) as client:
        response = client.get("https://api.cartola.globo.com/atletas/mercado")
        response.raise_for_status()
        data = response.json()

    clubes = data["clubes"]
    rows = []
    for atleta in data["atletas"]:
        clube = clubes.get(str(atleta["clube_id"]))
        if not clube:
            continue
        time_nome = CARTOLA_TEAM_NAMES.get(clube["abreviacao"])
        if not time_nome:
            continue
        rows.append((atleta["apelido"], atleta["nome"], time_nome))

    if not rows:
        raise ValueError("API do Cartola retornou lista de atletas vazia")
    return rows


def _load_players_from_csv():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "cartola_2026_jogadores_nome_posicao_time_20260804_122335.csv")
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [(row['apelido'], row['nome'], row['time']) for row in reader]


def load_player_reference():
    """Carrega o elenco atual (API do Cartola, com fallback pro CSV local se a API falhar) e retorna:
    - referencia: 'Apelido (Time): Nome completo' por linha
    - whisper_prompt: apelidos para guiar o Whisper
    - times_ref: jogadores agrupados por time
    """
    try:
        rows = _fetch_players_from_cartola_api()
        source = "API do Cartola (ao vivo)"
    except Exception as api_error:
        logger.warning(f"Falha ao buscar elenco ao vivo na API do Cartola, usando CSV local de fallback: {api_error}")
        try:
            rows = _load_players_from_csv()
            source = "CSV local (fallback, pode estar desatualizado)"
        except Exception as csv_error:
            logger.warning(f"CSV de fallback tambem falhou ao carregar: {csv_error}")
            return "", "", ""

    ref, whisper, team_ref, n_players, n_teams = _build_reference_strings(rows)
    logger.info(f"Elenco carregado via {source}: {n_players} jogadores, {n_teams} times")
    return ref, whisper, team_ref


JOGADORES_REFERENCIA, WHISPER_NAMES, TIMES_REFERENCIA = load_player_reference()

JOGADORES_LIST = "Abel Ferreira, Acevedo, Ademir, Adonis Frías, Adson, Aguirre, Alan Franco, Alan Patrick, Alan Rodríguez, Alerrandro, Alef Manga, Alisson, Alex Sandro, Alex Telles, Alexander Barboza, Alexsander, Alix Vinicius, Allan, André, André Luis, André Ramalho, Andreas Pereira, Andrew, Andrey Fernandes, Angileri, Anthoni, Ararat, Arboleda, Arias, Arthur, Arthur Cabral, Arthur Dias, Arthur Izaque, Arthur Melo, Arthur Novaes, Artur, Arrascaeta, Ayrton Lucas, Bastos, Batata, Belé, Benassi, Benavídez, Benedetti, Bernal, Bernabei, Bernard, Bobadilla, Bolasie, Borré, Braithwaite, Brayan, Breno Bidon, Breno Lopes, Bruno Alves, Bruno Fuchs, Bruno Gomes, Bruno Henrique, Bruno Leonardo, Bruno Melo, Bruno Pacheco, Bruno Rodrigues, Bruno Tabata, Bruninho, Cacá, Caio Alexandre, Caio Paulista, Caíque, Calleri, Camilo, Camutanga, Canobbio, Cantalapiedra, Cantillo, Carlos Cuesta, Carlos Eduardo, Carlos Miguel, Carlos Vinícius, Carlinhos, Carrascal, Carrillo, Cássio, Cassierra, Cauan Baptistella, Cauê, Cauly, Cédric Soares, Charles, Chico da Costa, Chico Kim, Chris Ramos, Christian, Claudinho, Clayton Sampaio, Cleiton, Coronel, Cristhian Loor, Cristian Olivera, Cuello, Cuiabano, Cufré, Da Mata, Danilo, Daniel Borges, Daniel Fuzato, Daniel Silva, Danielzinho, David, David Duarte, David Ricardo, Davi Gomes, De la Cruz, Dell, Denilson, Diego, Diego Hernández, Dieguinho, Diógenes, Djhordney, Dodi, Dória, Dorival Júnior, Douglas Telles, Dudu, Dyogo Alves, Edenílson, Edson Carioca, Edu, Eduardo, Eduardo Domínguez, Eduardo Doma, Eduardo Sasha, Eduardo Santos, Emerson Royal, Emiliano Martínez, Emmanuel Martínez, Enamorado, Ênio, Enzo Díaz, Enzo Vagner, Erick, Erick Pulga, Eric Ramires, Escobar, Esquivel, Everaldo, Everson, Everton, Everton Galdino, Everton Ribeiro, Evertton Araújo, Fabinho, Fábio, Fabri, Fabrício, Fabrício Bruno, Fagner, Felipe Anderson, Felipe Chiqueti, Felipe Guimarães, Felipe Jonatan, Felipe Longo, Felipe Negrucci, Felipinho, Félix Torres, Fernando, Fernando Pradella, Fernando Seabra, Fernando Sobral, Ferraresi, Ferreira, Fintelman, Flaco López, Fredi Lippert, Freitas, Freytes, Gabriel, Gabriel Abdias, Gabriel Bontempo, Gabriel Brazão, Gabriel Delfim, Gabriel Grando, Gabriel Leite, Gabriel Mec, Gabriel Menino, Gabriel Paulista, Gabriel Xavier, Galeano, Ganso, Garcez, Garro, Gerson, Giay, Gilberto, Gilmar Dal Pozzo, Giovanni Augusto, Giovanni Pavani, Guga, Gui Negão, Guilherme Arana, Guilherme Gomes, Gustavinho, Gustavo, Gustavo Henrique, Gustavo Martins, Gustavo Prado, Gustavo Scarpa, Gustavo Talles, Guzmán Rodríguez, Habraão, Hércules, Herrera, Higor Meritão, Hulk, Hugo, Hugo Moura, Hugo Souza, Iago, Igor Cariús, Igor Formiga, Igor Gomes, Igor Rabello, Igor Vinícius, Ignácio, Ignacio Sosa, Índio, Isaac, Isidro Pitta, Ítalo, Ivan, Iván Román, Jacy, Jáderson, Jair, Jair Ventura, Jajá, Jamerson, Janderson, Japa, Jean Carlos, Jean Gabriel, Jean Lucas, Jefté, Jefinho, Jeferson, Jeffinho, Jemmes, Jhoan Hernández, João Ananias, João Basso, João Bezerra, João Bom, João Cruz, João Lucas, João Marcelo, João Paulo, João Pedro, João Schmidt, João Victor, João Vitor, Joaquín Correa, Johan Rojas, John Kennedy, Jonathan Jesus, Jorginho, Josué, JP, JP Chermont, Juan Vojvoda, Julimar, Júnior Santos, Juninho, Juninho Capixaba, Junior Alonso, Justino, Kadir, Kaiki Bruno, Kainã, Kaio, Kaio César, Kaio Jorge, Kaique Kenji, Kaiquy Luiz, Kannemann, Kanu, Kauã Moraes, Kauã Pascini, Kauã Prates, Kauan, Kauan Toledo, Kauê Furquim, Kayke, Kayky, Kayky Almeida, Keno, Keven Samuel, Khellven, Kike Saverio, Klaus, Labyad, Larson, Lavega, Lawan, Léo, Léo Andrade, Léo Derik, Léo Jardim, Léo Linck, Léo Nannetti, Léo Ortiz, Léo Pereira, Léo Vieira, Leozinho, Leonel Pérez, Luan, Luan Cândido, Luan Freitas, Luan Peres, Lucas Arcanjo, Lucas Barbosa, Lucas Cunha, Lucas Evangelista, Lucas Freitas, Lucas Moura, Lucas Mugni, Lucas Oliveira, Lucas Paquetá, Lucas Piton, Lucas Romero, Lucas Ronier, Lucas Silva, Lucas Taverna, Lucca, Luciano, Luciano Juba, Lucão, Lucho Acosta, Luighi, Luis Miguel, Luis Zubeldía, Luiz Araújo, Luiz Felipe, Luiz Gustavo, Lyanco, Maicon, Maik, Mailson, Mancha, Marçal, Marcelinho, Marcelo Eráclito, Marcelo Lomba, Marcelo Pitaluga, Marcelo Rangel, Marcão, Marcinho, Marcos Alexandre, Marcos Antônio, Marcos Rocha, Marcos Vinícius, Marinho, Marino Hinestroza, Marlon, Marlon Freitas, Marllon, Marquinhos, Martín Anselmi, Martinelli, Mastriani, Mateus Carvalho, Mateus Dias, Mateus Iseppe, Mateus Silva, Mateus Xavier, Matheus Bahia, Matheus Bidu, Matheus Cunha, Matheus Donelli, Matheus Fernandes, Matheus França, Matheus Henrique, Matheus Martins, Matheus Pereira, Matheus Reis, Matheus Soares, Matheuzinho, Maurício, Maycon, Mayke, Medina, Memphis Depay, Mendoza, Mercado, Michel Araújo, Miguelito, Minda, Moisés, Monsalve, Montoro, Murilo, Murilo Rhikman, Mycael, Nadson, Nardoni, Natanael, Nathan, Nathan Fogaça, Nathan Mendes, Negueba, Neris, Neto, Neto Moura, Neto Pessoa, Newton, Neymar, Nicolas Pontes, Nicolás Ferreira, Nonato, Noriega, Nuno Moreira, Oliva, Osvaldo, Otávio, Pablo Baianinho, Pablo Lúcio, Pablo Maia, Palacios, Panagiotis, Patrick, Patrick de Paula, Paulinho, Paulo Henrique, Paulo Pezzolano, Pavón, Pedro, Pedro Cobra, Pedro Ferreira, Pedro Henrique, Pedro Kauã, Pedro Morisco, Pedro Raul, Pedro Rocha, Perotti, PH Gama, Phillipe Gabriel, Picco, Piquerez, Plata, Portilla, Praxedes, Preciado, Puma Rodríguez, Rafael, Rafael Carvalheira, Rafael Guanaes, Rafael Monti, Rafael Santos, Rafael Soares, Rafael Thyere, Rafael Tolói, Raniele, Raul, Rayan Lelis, Raykkonen, Reinaldo, Renan Lodi, Renan Peixoto, Renan Viana, Renato Kayzer, Renato Marques, Renê, Renzo López, Rhuan Gabriel, Riccieli, Richard, Riquelme, Riquelme Fillipi, Riquelme Felipe, Robert, Robert Renan, Robinho Jr., Rochet, Rodrigo Moledo, Rodrigo Nestor, Rodrigo Rodrigues, Rodrigues, Roger, Rogério Ceni, Rollheiser, Román Gómez, Ronald, Ronald Lopes, Ronaldo, Rony, Rossi, Ruan, Ruan Assis, Ruan Pablo, Rúben Ismael, Rubens, Ryan, Ryan Francisco, Sabino, Saldivia, Samuel Lino, Samuel Xavier, Sanabria, Santi Moreno, Santi Rodríguez, Santiago Mingo, Santos, Sant Anna, Saúl, Sávio, Savarino, Sebastián Gómez, Serna, Shaylon, Sinisterra, Soteldo, Souza, Spinelli, Tassano, Tchê Tchê, Terán, Tetê, Tevis, Thaciano, Thalisson Gabriel, Thiago Azaf, Thiago Beltrame, Thiago Couto, Thiago Maia, Thiago Mendes, Thiago Santos, Thomazella, Tiago Cóser, Tiago Volpi, Tiaguinho, Tico, Tiquinho Soares, Tite, Tomás Pérez, Tinga, Vanderlan, Varela, Vegetti, Viery, Villalba, Villasanti, Villagra, Villarreal, Vini Paulista, Vinicinho, Vinicius, Vinicius Lira, Vitão, Vitinho, Vitor Bueno, Vitor Eudes, Vitor Gabriel, Vitor Hugo, Vitor Roque, Viveros, Wagner Leonardo, Walace, Wallace Davi, Wallace Yan, Wallisson, Walter, Walter Clar, Wanderson, Weverton, Wendell, Wesley Natã, Willian, Willian Arão, Willian José, Willian Machado, Willian Oliveira, Yago Ferreira, Yago Pikachu, Ygor Vinhas, Ythallo, Yuri Alberto, Yuri Lara, Yuri Leles, Zé Breno, Zé Guilherme, Zé Ivaldo, Zé Marcos, Zé Ricardo, Zé Rafael, Zapelli"

NAMES_CORRECTION_PROMPT = f"""Você é um especialista em correção de nomes de jogadores de futebol brasileiro em transcrições de áudio.

CONTEXTO:
A transcrição foi gerada pelo Whisper (reconhecimento de fala). O Whisper escreve nomes foneticamente — frequentemente errado. Seu trabalho é identificar e corrigir esses erros usando a referência oficial abaixo.

TAREFA:
Devolver a MESMA transcrição, corrigindo APENAS nomes de jogadores, técnicos e times quando houver erro claro de reconhecimento.

REGRAS GERAIS:
1. Não resuma, não reorganize, não reescreva frases.
2. Não mude pontuação, estrutura ou sentido.
3. Preserve todo o restante do texto exatamente como veio.
4. Quando um time for mencionado no contexto, consulte a seção "ELENCOS POR TIME" para identificar qual jogador é o correto — use o elenco do time como chave de desambiguação.
5. Se houver dúvida real entre dois jogadores distintos sem contexto de time, mantenha como está.
6. Nunca invente um nome que não esteja na referência abaixo.
7. Para nomes de times, corrija apenas quando houver erro claro do Whisper. Não troque uma forma válida por outra só por padronização.
8. A REFERÊNCIA OFICIAL e os ELENCOS POR TIME podem estar desatualizados (jogadores mudam de time ao longo da temporada). Nunca troque um jogador por outro jogador de um time diferente só porque a referência diz que ele joga naquele time — isso pode estar errado. Use o elenco apenas para desambiguar entre nomes foneticamente parecidos, nunca para "corrigir" um jogador para outro por causa do time. Na dúvida entre confiar na referência desatualizada ou no que foi dito no áudio, preserve o nome exatamente como veio na transcrição.

ERROS CONHECIDOS DO WHISPER — CORRIJA SEMPRE:
- "Caio Jorge" → "Kaio Jorge" (não existe Caio Jorge no Brasileirão)
- "Cauã Moraes" → "Kauã Moraes" (Bahia)
- "Cauã Prates" → "Kauã Prates"
- "Cauã Pascini" → "Kauã Pascini"
- "Cauan" sem sobrenome → verifique: se for Baptistella, mantém com C; qualquer outro Kauã começa com K
- "Gêmeos" ou "Gêmos" → "Jemmes" (jogador do Fluminense)
- "Lúcio" quando referente ao Fluminense → "Lucho Acosta"
- "Tassiano" ou "Taciano" → "Thaciano"
- "Alan" pode ser "Allan" — verifique pelo time: Allan joga no Flamengo; Alan Patrick no Internacional
- "Mateus" vs "Matheus" — verifique pelo time na seção de elencos abaixo
- "Dorival Júnior" é técnico da Seleção Brasileira, NÃO é técnico de clube no Brasileirão 2026. Se aparecer como técnico de um clube, corrija pelo nome real do técnico daquele clube (use o contexto do áudio).

REFERÊNCIA OFICIAL (Apelido · Time · Nome completo — use o time para desambiguar pelo contexto do áudio):
{JOGADORES_REFERENCIA if JOGADORES_REFERENCIA else JOGADORES_LIST}

ELENCOS POR TIME:
{TIMES_REFERENCIA if TIMES_REFERENCIA else "Sem referência adicional por time."}

SAÍDA:
- Devolva apenas a transcrição corrigida.
- Nenhum comentário. Nenhuma explicação.
"""

LEGACY_SYSTEM_PROMPT = f"""Você converte transcrições de áudio em legendas para um grupo de Telegram de análise do Cartola FC.

## REGRAS DE OURO

1. **Fidelidade total e absoluta**: escreva APENAS o que foi dito. Proibido inferir, deduzir ou inventar qualquer conteúdo — mesmo que pareça lógico ou esperado. Se o áudio não disse, a legenda não diz. Isso inclui causas, consequências, contextos e adjetivos que não foram pronunciados.
2. **Síntese inteligente**: identifique os 2 a 4 pontos centrais do áudio e construa a legenda em torno deles. Corte repetições, vícios de linguagem e raciocínios intermediários. Mas preserve o sentido completo de cada ideia — nunca fragmente uma frase a ponto de ela perder o significado.
3. **Tamanho proporcional, sempre enxuto**: prefira legendas curtas, mas não a qualquer custo. Cada frase deve ter sentido completo. Se precisar de uma linha a mais para que a ideia faça sentido, use. O que não cabe é redundância — não frase incompleta.
4. **Sem linguagem artificial**: evite frases como "Em resumo", "Portanto", "Vale ressaltar", "Essa análise mostra", "Boa sorte", "Fique atento" e semelhantes, a menos que isso tenha sido dito no áudio.
5. **A legenda termina quando o conteúdo essencial termina.** Sem frase de encerramento automática.
6. **Nomes de jogadores**: se o nome estiver claramente identificável na transcrição, use a grafia correta da lista abaixo.
7. **Nunca troque um jogador por outro por suposição.** Se houver dúvida real, preserve o nome como veio na transcrição, sem inventar correção.
8. Não crie seções artificiais como "Conclusão", "Materiais e métodos", "Metodologia", "Panorama", "Síntese" ou semelhantes, a menos que isso tenha sido dito no áudio.
9. Não use metáforas, abstrações ou floreios como "mosaico de informações", "cenário em construção", "retrato do momento" e semelhantes, a menos que isso tenha sido dito no áudio.
10. Prefira linguagem direta, concreta e próxima da fala do áudio.
11. Não transforme a legenda em texto de artigo, relatório acadêmico ou análise formal demais.
12. Não reconte o raciocínio passo a passo. Vá direto à conclusão do raciocínio.
13. Se o ponto principal e suas ressalvas couberem em 3 a 5 linhas, prefira esse tamanho.
14. Subtítulos só quando o áudio tiver blocos claramente distintos. Nunca para enfeitar.

## FORMATAÇÃO HTML (Telegram)
- Pode usar emojis de forma útil e natural.
- Pode usar destaques com CAIXA ALTA.
- Pode usar <b>negrito</b> para nomes, times, conceitos e pontos fortes.
- Pode usar <i>itálico</i> para ressalvas, nuances e observações.
- Pode usar <b><i>negrito itálico</i></b> quando houver um destaque central realmente importante.
- NÃO use Markdown com asteriscos ou underscores. Use apenas HTML.
- NÃO exagere na quantidade de destaques.

## ESTILO ESPERADO
- A legenda deve soar como o próprio locutor escrevendo — preserve o tom, o ritmo e a entonação da fala. Se ele fala com energia, a legenda tem energia. Se ele faz ressalvas, as ressalvas aparecem.
- **Prefira o formato de tópicos com bullets** — é mais legível no Telegram e mais próximo do estilo do locutor.
- **Cada bullet deve ter verbo e contexto mínimo** para fazer sentido sozinho. O formato ideal é "Nome/assunto: frase curta com verbo." Exemplos certos:
  - ✅ "Lucas Veríssimo: Segurança defensiva, salvou gol certo do Tagliari."
  - ✅ "4-4-2: É um esquema mais equilibrado, sem abrir mão dos laterais, numa rodada com menos opções de atacantes."
  - ✅ "3-4-3: Rodada com excelentes opções de meias — Arias, Neymar, Allan, Paquetá. Dentre eles, dois indicados para capitão."
- Bullets curtos são bem-vindos quando o contexto já está claro. O que não pode é bullet vazio de significado como "Menos atacantes de peso" ou "Equilíbrio com laterais".
- Use conectores naturais do português falado: "Dentre eles", "Além disso", "sem abrir mão de", "numa rodada que".
- A legenda deve parecer feita por alguém que ouviu com atenção, entendeu e organizou — não por alguém que preencheu um formulário.

## PADRÃO DE SAÍDA DESEJADO
- Comece sempre com um título curto e direto (emoji + negrito).
- Use subtítulos só se o áudio tiver 2 ou mais blocos distintos de assunto.
- Tom entre o sóbrio e o comunicativo — nunca frio, nunca exaltado.
- Use emojis com critério e variedade — escolha conforme o conteúdo da seção, não repita sempre os mesmos. Exemplos de uso contextual: ⚽ para jogo/análise, 🔍 para destaques individuais, 📌 para observações táticas, 🏆 para impacto no fantasy, 🟢🟡🔴 para semáforo de favoritismo, 🎯 para dicas, 💡 para insights, ⚠️ para alertas, 🔝 para melhores opções, 🛡️ para defesa, ⚡ para jogadores em forma. Adapte ao que faz sentido para cada áudio.
- Negrito para nomes, times e pontos-chave. Itálico para ressalvas e nuances.
- A legenda deve ter ritmo visual: frases curtas, espaço entre blocos, fácil de varrer os olhos.

## EXEMPLOS REAIS (aprenda o estilo com estes dois casos)

### EXEMPLO 1

**TRANSCRIÇÃO:**
Bom pessoal, vamos lá então começar a fazer a nossa análise dos confrontos aqui, ainda que um pouco tardiamente, pelos imprevistos aqui que eu tive, mas vamos em frente. Seguinte, por que eu considero o Fluminense aqui favorito, jogo de faixinha verde, entre aspas, na minha análise do semáforo? E talvez não um outro time mais favorito na rodada, apesar de que eles existem. O Fluminense hoje, para mim, é um dos times mais organizados do Campeonato Brasileiro. O time que tem uma organização tanto defensiva quanto de transição ofensiva muito bem padronizada, um time que não se expõe muito. O time do Fluminense, você percebe que quando o time do Fluminense está jogando, ele toma todo o cuidado do mundo para só sair para o ataque se ele estiver totalmente organizado na defesa. E uma vez que o Fluminense perde a bola, ele faz um perde e pressiona muito rápido, justamente para evitar que a sua linha defensiva fique mais exposta lá atrás. Então ele tenta recuperar a bola na zona de menor perigo possível. Ainda assim, quando o Fluminense é atacado no seu último terço de campo, porque eles gostam de usar essa linguagem tática, quase sempre o Fluminense está muito bem protegido. O Zubel Dias já cuidou de fazer o ajuste defensivo do Fluminense depois da saída do Thiago Silva, que foi uma coisa que a gente detectou, que o Fluminense sentiu um pouco a saída dele. E hoje o Fluminense é um time bem organizado defensivamente. O Fluminense saiu para jogar contra o Remo, não poupou o time de maneira muito contundente. Teve ali praticamente seu time principal jogando contra o Remo lá no Pará, depois de uma final contra o Flamengo, que foi bastante cansativa, mas o Fluminense havia poupado o time contra o Palmeiras, então a gente não tem um Fluminense assim tão cansado. Além disso, o Fluminense joga no Maracanã, então não é momento do Fluminense poupar energia. Esses jogos são os jogos que o Fluminense tem que ganhar se ele quiser disputar a Libertadores, disputar a título, entendeu? Então a gente precisa ter esse nível de confiança no Fluminense justamente nesses jogos em que ele tem necessidade de vencer, tá bom? O time do Atlético Paranaense não é um time que tem demonstrado tanta fragilidade assim. Saiu para enfrentar o Red Bull Bragantino e teve em alguns momentos, não sei se vocês lembram, mas o jogo estava com muita chuva, não sei se vocês recordam disso, mas o time do Atlético Paraná esteve em alguns momentos até o domínio do jogo sobre o time do Red Bull Bragantino, mas não conseguiu vencer, apenas empatou, o que está longe de ser um resultado ruim. Ruim mesmo foi ter perdido em casa para o Corinthians, aquela derrota para o Corinthians em casa realmente foi bastante inesperada e o time fez um bom jogo naquela ocasião, mas perdeu um caminhão de gols, teve ali um xg muito alto, eu lembro que foi um amasso do time do Atlético Paranaense no Corinthians, mas o time não conseguiu marcar gols. Como o Fluminense é um time organizado e o Atlético Paranaense tem essa característica, É um jogo que eu acho que passa para a gente uma certa segurança em relação até a linha defensiva do Fluminense. Claro, é garantido que o Fluminense vai ficar sem sofrer gol. Não, garantido não tem nada no Campeonato Brasileiro. Mas a gente tem que analisar, tem que encontrar padrões, comparar com outros jogos e tomar decisões. Então, para mim, aqui, Fluminense é favorito e eu acho importante a gente olhar, sim, para a linha defensiva do Fluminense.

**LEGENDA CORRETA:**
🎙 <b>PRÉ-ANÁLISE FLUMINENSE x ATHLETICO-PR</b>

🟢 <b><i>FLUMINENSE FAVORITO — O JOGO DE FAIXINHA VERDE DA RODADA</i></b>

O <b>Fluminense</b> é <i>um dos times mais organizados do campeonato</i>. Defensivamente e em transição ofensiva, tudo muito bem padronizado.

Só sai pro ataque quando está totalmente organizado na defesa. Perdeu a bola? Perde e pressiona rápido, recupera na zona de menor perigo. Quando é atacado no último terço, <i>quase sempre está bem protegido</i>.

<b>Zubeldia</b> já fez o ajuste defensivo pós-saída do <b>Thiago Silva</b>. Time sentiu no começo, mas hoje está encaixado.

⚽ <b>DESGASTE FÍSICO?</b>

Fluminense não poupou contra o <b>Remo</b> (no Pará), mas <i>havia poupado contra o Palmeiras</i>. Não está tão cansado. Joga no Maracanã. Precisa vencer se quiser disputar Libertadores e títulos. <i>Não é hora de poupar.</i>

⚽ <b>ATHLETICO-PR</b>

Não é time frágil. Empatou com o <b>Bragantino</b> (sob chuva forte, chegou a dominar o jogo). A derrota em casa pro <b>Corinthians</b> foi inesperada: <i>amassou o Corinthians, xG altíssimo, mas não fez gol.</i>

Essa é a característica do <b>Athletico-PR</b>: produz, mas peca na finalização.

📌 <i>Fluminense organizado vs Athletico-PR que não converte. Cenário favorável pra olhar a <b>LINHA DEFENSIVA</b> do Fluminense com confiança.</i>

Garantido? Nada é no Brasileirão. Mas padrões e comparações apontam pro <b>Flu</b>.

---

### EXEMPLO 2

**TRANSCRIÇÃO:**
Bom pessoal, estou colocando para vocês aí a nossa análise do semáforo, aí sim eu tenho a minha opinião, eu espero que isso fique claro para vocês, que quando eu coloco as probabilidades da rodada, aquilo ali não é a minha opinião, aquilo ali são as bolsas esportivas, é a opinião deles, beleza? Eu sempre tenho muito receio das pessoas que não ouvem os meus áudios, não acompanham o meu raciocínio, porque vocês podem criar um certo tipo de confusão a respeito do que eu estou colocando, tá bom? Mas, enfim, estou fazendo o meu papel aqui. Na análise do semáforo, eu tenho um recorte aqui de pelo menos 5 times que eu considero favoritos na rodada, cada um com seu grau de favoritismo. Para mim, o maior favorito da rodada é o Fluminense, pelo que o time vem jogando, pelas atuações defensivas do time do Fluminense, pelo peso do Maracanã e etc. Com isso, eu não estou, entre aspas, desdenhando do Atlético Paranaense, tá? O Atlético Paranaense não é um time horroroso, não é um time fraco, não é um time ruim defensivamente, não. Mas o Fluminense já deu mostras que é um time que, em casa, precisa ser olhado com bastante carinho, tá bom? Palmeiras contra o Mirasol, para mim, também é um grande favorito da rodada, o segundo maior favorito da rodada. Só não vou colocar ali o Palmeiras como o maior favorito da rodada, porque a Chapecoense é um time enjoado de ser enfrentado. É um time chatinho, o Guanais é muito estratégico nas suas montagens de time e eles estão acostumados a se enfrentar. Isso também tem um peso, na medida que os técnicos vão se enfrentando cada vez mais, eles vão aprendendo a se anular nas suas características positivas, explorar as negativas, por isso que eu acho que o Palmeiras leva vantagem. O Palmeiras tem mais qualidade do que o time do Mirassol. O time do Mirassol vem falhando muito defensivamente em alguns momentos. Gosto do time do Coxa. Não acho que, por exemplo, o Cruzeiro é mais favorito do que o Coxa. Vendo o time do Remo jogar, o time do Coxa vem embalado por uma boa vitória contra o time do Corinthians. contra o Remo é um time que a gente tem que explorar. Pelo que eu tenho visto da Chapecoense, o Grêmio para mim é favorito, Chapecoense muito, muito limitada defensivamente, vem tomando caminhões de gol dentro de casa e o Grêmio ofensivamente tem sido um time muito produtivo, então para mim o Grêmio é favorito contra a Chape. E aí o quinto time ali que eu coloco como dentro de um hall de favoritos na rodada é o Cruzeiro contra o Vasco, mas aqui guardadas as devidas proporções de favoritismo, não acho que o Cruzeiro é tão favorito, por exemplo, quanto eu considero o Palmeiras, o próprio Fluminense, porque o Vasco, com a chegada do Renato Gaúcho, tende a ser um time que se protege um pouco melhor, um pouco mais estratégico também, em termos de planejamento tático para os jogos. Então isso gera um certo desconforto ali para a gente olhar para o Cruzeiro Ele cravar um favoritismo gigantesco. Até porque o time do Cruzeiro nas mãos do Tite ainda está em fase de construção. É lanterna do campeonato. Então a gente tem que ter um pouco de cuidado para não escalar o Cruzeiro do nosso imaginário. A gente tem que escalar o Cruzeiro real contra o Vasco real. O Cruzeiro hoje tem condição plena de vencer o Vasco, principalmente jogando no Mineirão. Mas não dá para a gente achar que esse Cruzeiro é o Cruzeiro do Leonardo Jardim, cara. Não é, é o Cruzeiro do Tite. Então a gente tem que tomar um certo cuidado com isso. Os jogos ali, do Internacional para cima, tem os seus favoritismos. Eu acho até que, por exemplo, São Paulo é favorito contra o Bragantino, mas uma coisa bem leve. Flamengo contra o Botafogo, mas uma coisa bem leve. Santos e Corinthians eu já acho mais parelho. Internacional e Bahia também. Beleza?

**LEGENDA CORRETA:**
🎙 <b>SEMÁFORO DA RODADA — OPINIÃO PESSOAL</b>

📌 <i>Diferente das probabilidades (mercado), aqui é a minha leitura.</i>

🟢 <b>TOP 5 FAVORITOS DA RODADA</b>

1️⃣ <b>Fluminense</b> — <i>maior favorito da rodada</i>
Atuações defensivas consistentes, peso do Maracanã. O Athletico-PR não é time fraco, mas o Fluminense em casa precisa ser olhado com carinho.

2️⃣ <b>Palmeiras</b> (vs Mirassol)
Qualidade superior. Mirassol vem falhando defensivamente. Só não é o 1° porque a Chapecoense é time enjoado e o Guanais é estratégico nas montagens. Técnicos que se enfrentam muito vão aprendendo a se anular.

3️⃣ <b>Coritiba</b> (vs Remo, no Couto Pereira)
Vem embalado pela vitória contra o Corinthians. Vai ter que ser protagonista e isso nem sempre é fácil pro Coxa. Mas contra o Remo em casa é jogo pra explorar.

4️⃣ <b>Grêmio</b> (vs Chapecoense)
Chape <i>muito limitada defensivamente</i>, tomando caminhões de gol. Grêmio ofensivamente produtivo. Favoritismo claro.

5️⃣ <b>Cruzeiro</b> (vs Vasco) — <i>com ressalvas</i>
Cruzeiro é lanterna, ainda em fase de construção nas palavras do Tite. Vasco com Renato Gaúcho tende a se proteger melhor e ser mais estratégico. <i>Não dá pra escalar o Cruzeiro do imaginário. É o Cruzeiro do Tite, não o do Leonardo Jardim.</i>

🟡 <b>DEMAIS JOGOS</b>

São Paulo favorito contra o Bragantino, mas <i>leve</i>
Flamengo favorito contra o Botafogo, mas <i>leve</i>
Santos x Corinthians — <i>parelho</i>
Internacional x Bahia — <i>parelho</i>

---

## AGORA É SUA VEZ

### EXEMPLO 3 — ATENÇÃO AO ESTILO DE FRASE (compare gerado vs. correto)

**LEGENDA GERADA (ERRADA — estilo telegráfico e nominal):**
🎯 <b>DICAS POR POSIÇÃO — RODADA ATUAL</b>

📌 <b>Esquemas Táticos</b>
- 3-4-3: Forte no meio-campo com Arias, Neymar, Allan, Jean Lucas, Paquetá e Acosta. Dois com recomendação de capitão.
- 4-4-2: Equilíbrio com laterais escaláveis. Menos atacantes de peso.
- 3-5-2: Também viável.

📌 <b>Defensivamente</b>
- Destaque para jogadores de Palmeiras, Flamengo, Cruzeiro e Bahia.
- Santos e Botafogo: Menos explorados. Igor Vinícius e Ferraresi por boas médias. Ignácio é barato e bom em desarmes.

**LEGENDA CORRETA (estilo do locutor — frases completas, com contexto e conectores):**
🎯 <b>DICAS POR POSIÇÃO — RODADA ATUAL</b>

📌 <b>Esquemas Táticos</b>
- 3-4-3: Rodada com excelentes opções de meias para escalar como <b>Arias, Neymar, Allan, Jean Lucas, Paquetá e Acosta</b>. Dentre eles, dois como indicados para capitão.
- 4-4-2: É um esquema mais equilibrado, sem abrir mão dos laterais, <i>numa rodada com menos opções de atacantes</i>.
- 3-5-2: Também é um esquema viável.

📌 <b>Defensivamente</b>
- Destaque para jogadores de <b>Palmeiras, Flamengo, Cruzeiro e Bahia</b>.
- Santos e Botafogo: Estão menos explorados na rodada. <b>Igor Vinícius</b> e <b>Ferraresi</b> são boas opções por suas médias. <b>Ignácio</b> é barato e bom em desarmes.

---

A transcrição do usuário vem a seguir. Siga o estilo dos exemplos acima — especialmente o EXEMPLO 3. Use frases com verbo, adicione contexto nos bullets, preserve o tom do locutor.
"""

# ── Servidor HTTP para health check ──────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

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


SYSTEM_PROMPT = """
Voce cria legendas em HTML para Telegram a partir de uma transcricao ja corrigida.

<objetivo>
Transforme a fala em uma legenda curta, fiel, humana e facil de escanear no celular, com cara de texto escrito pelo proprio locutor.
</objetivo>

<regras_inviolaveis>
- Use apenas informacoes ditas na transcricao.
- Nao invente contexto, causa, consequencia, comparacao, estatistica ou conclusao que nao foi falada.
- Use exatamente os nomes de jogadores, tecnicos e times como aparecem na transcricao recebida.
- Se um nome estiver ambiguo, preserve como veio na transcricao.
- E permitido reorganizar a ordem das ideias dentro do mesmo assunto/bloco do audio.
- NUNCA combine, compare ou misture conclusoes, ressalvas ou argumentos de blocos/assuntos diferentes do audio. Cada conclusao fica associada exatamente ao assunto sobre o qual ela foi dita. Misturar blocos pode inverter o que o locutor quis dizer.
- Resuma removendo repeticao, muleta e desvios, sem amputar a ideia principal.
- Fidelidade e obrigatoria; cronologia literal nao e obrigatoria dentro do mesmo bloco.
</regras_inviolaveis>

<formato>
- Responda apenas com HTML valido para Telegram.
- Abra com um titulo obvio em CAIXA ALTA: emoji + <b>TITULO</b>.
- O emoji do titulo deve vir antes do <b>, nunca depois do texto.
- O titulo deve refletir de forma direta o tema que o locutor introduziu. Nao invente titulo criativo.
- Siga o orcamento informado junto da transcricao. Ele e limite, nao meta para preencher.
- Organize a legenda em 2 ou 3 blocos por padrao. Use 4 apenas se o audio trouxer ideias centrais realmente distintas.
- Use subtitulos funcionais em CAIXA ALTA quando ajudarem a entender os blocos, mas evite cara de slide, apostila ou relatorio.
- Use emojis com parcimonia: 1 no titulo e no maximo 1 ou 2 em subtitulos realmente importantes. Em ambos, o emoji vem antes do <b>.
- Nunca comece bullets com emoji. Bullet usa apenas "-"; o destaque visual fica no <b>, <i> e na frase.
- Prefira 3 a 5 bullets no total. Em audio longo, pode chegar ao limite informado se isso evitar amputar ideias.
- Cada bullet precisa ter verbo e contexto minimo para fazer sentido sozinho.
- Cada bullet deve caber em uma frase principal. So use uma segunda oracao curta se sem ela a ideia ficar manca.
- A pontuacao deve ser natural e ajudar o texto a respirar.
- Se varios exemplos sustentam o mesmo ponto, escolha o mais forte em vez de listar todos.
- Cada bloco deve ser enxuto: 1 ou 2 bullets fortes, sem texto amontoado.
- Use <b> para nomes, times e pontos-chave.
- Use <i> para ressalvas, nuances e alertas.
- Use poucos emojis, com criterio. A legenda nao deve parecer uma lista de icones.
- Nunca use Markdown com asteriscos ou underscores.
- Nao termine com frase automatica de encerramento.
- A legenda inteira deve parecer limpa em um print do Telegram, nao um artigo espremido.
- Se estiver ficando grande demais, compacte listas e detalhes repetidos, mas preserve a conclusao e a ressalva que mudam a decisao.
</formato>

<estilo>
- Direto, natural e vivo.
- Humano, nunca robótico.
- Frase completa, mas curta.
- Mesmo compacta, a legenda precisa soar fluida, bem pontuada e viva.
- Tom entre sobrio e comunicativo.
- Pode ter ritmo e personalidade visual, mas sem floreio literario.
- Soe como o proprio locutor escrevendo, nao como um redator externo nem como IA.
- Evite subtitulos secos demais como "CRITERIOS E EXEMPLOS PRATICOS", "AMPLITUDE DA ANALISE", "ANALISE COLETIVA E INTERPRETACAO DOS PERCENTUAIS" quando houver uma forma mais natural de dizer.
- Prefira subtitulos curtos, claros e vivos, como "COMO EU USO ISSO", "NA PRATICA", "PONTO DE ATENCAO", "ONDE EU GOSTO MAIS", se isso combinar com o audio.
- Evite jargoes artificiais e expressoes como "Em resumo", "Vale ressaltar", "Portanto", "Panorama" e similares, a menos que isso tenha sido dito.
- Evite bullets longos com varios nomes, varios numeros e varias ressalvas empilhadas.
</estilo>

<guia_de_frase>
Ruim: "- 4-4-2: Equilibrio com laterais."
Bom: "- 4-4-2: E um esquema mais equilibrado, sem abrir mao dos laterais, numa rodada com menos opcoes de atacantes."
Ruim: "<b>CRITERIOS E EXEMPLOS PRATICOS</b>"
Bom: "<b>COMO EU USO ISSO NA PRATICA</b>"
</guia_de_frase>

<checklist_interno>
Antes de responder, verifique em silencio:
1. Nenhum nome de time ou jogador foi trocado por memoria.
2. Nenhum ponto foi inventado.
3. Nenhuma conclusao ou ressalva foi misturada entre blocos/assuntos diferentes do audio.
4. Os bullets fazem sentido sozinhos.
5. O titulo esta obvio e fiel ao que o locutor introduziu.
6. Os subtitulos ajudam a leitura.
7. Os emojis sao poucos, combinam com o assunto e nao aparecem no inicio dos bullets.
</checklist_interno>
"""

ENTITY_FIDELITY_PROMPT = """
Voce recebe uma transcricao corrigida e uma legenda em HTML.

Sua tarefa e devolver a MESMA legenda, alterando apenas o que for necessario para garantir fidelidade total a nomes de jogadores, tecnicos e times.

Regras:
- Preserve a estrutura, os subtitulos, os emojis, o tom e o HTML da legenda.
- Corrija apenas nomes e trechos diretamente ligados a nomes.
- Se a legenda mencionar um nome que nao aparece de forma sustentada pela transcricao, substitua pelo nome correto da transcricao.
- Se nao houver nome correto claro na transcricao, remova apenas o fragmento problemático sem reescrever o restante.
- Nao invente nomes.
- Nao resuma de novo.
- Nao adicione comentarios.

Saida:
- Devolva apenas a legenda final em HTML.
"""

LEGEND_COMPACTION_PROMPT = """
Voce recebe uma transcricao corrigida e uma legenda em HTML para Telegram.

Sua tarefa e encurtar a legenda quando ela estiver grande demais, sem deixar o texto seco, robotico ou com cara de apostila.

Regras:
- Preserve o titulo principal, o tom humano e a organizacao por blocos.
- Preserve nomes de jogadores, tecnicos e times exatamente como aparecem.
- Preserve ou recoloque 1 emoji no titulo e no maximo 1 ou 2 emojis em subtitulos quando isso ajudar a leitura.
- O emoji de titulo e subtitulo deve vir antes do <b>, nunca depois do texto.
- Nunca comece bullets com emoji. Bullet usa apenas "-".
- Siga o orcamento informado pelo usuario. Fique abaixo do limite superior, mas nao esprema a ponto de perder ideias centrais.
- Mantenha 2 ou 3 blocos por padrao. Use 4 apenas se for indispensavel para nao cortar uma ideia central.
- Mire em 3 a 5 bullets no total. Em audio longo, use ate o limite informado se necessario.
- Cada bullet deve ter uma frase principal. So use uma segunda oracao curta se ela for indispensavel.
- Mantenha a pontuacao natural, com leitura fluida.
- Corte exemplos redundantes, listas extensas, explicacoes que repetem a mesma ideia e excesso de numeros.
- Encurte dentro dos bullets, nao cortando a identidade visual da legenda.
- Se dois bullets disserem quase a mesma coisa, una ou elimine o mais fraco.
- Nao invente nada, nao troque nomes e nao mude o sentido do audio.
- Nao transforme a legenda em texto frio ou generico.
- Devolva apenas HTML valido para Telegram.
"""


# ── Funções de transcrição, correção de nomes e legendagem ───────────────────

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    duration_seconds: int | None = None,
    mime_type: str | None = None,
) -> str:
    filename = _safe_audio_filename(filename, mime_type, "audio.ogg")
    mime_type = _audio_mime_type(filename, mime_type)
    timeout = get_transcription_timeout(duration_seconds)
    logger.info(
        "Chamando transcrição OpenAI | model=%s filename=%s mime=%s bytes=%s timeout=%ss",
        OPENAI_TRANSCRIPTION_MODEL,
        filename,
        mime_type,
        len(audio_bytes),
        timeout,
    )

    audio_io = io.BytesIO(audio_bytes)
    response = _post_openai(
        "https://api.openai.com/v1/audio/transcriptions",
        timeout=timeout,
        action_name="transcrição",
        files={"file": (filename, audio_io, mime_type)},
        data={
            "model": OPENAI_TRANSCRIPTION_MODEL,
            "language": "pt",
            "prompt": f"Cartola FC, Campeonato Brasileiro. Nomes: {WHISPER_NAMES[:400]}"
        }
    )
    return response.json()["text"]


def correct_player_names(transcript: str) -> str:
    return _chat_completion_with_auto_continue(
        action_name="correcao de nomes",
        timeout=180.0,
        model=OPENAI_NAMES_MODEL,
        messages=[
            {"role": "system", "content": NAMES_CORRECTION_PROMPT},
            {"role": "user", "content": transcript}
        ],
        temperature=0,
        max_tokens=get_name_correction_max_tokens(transcript),
        continue_instruction=(
            "Continue exatamente da proxima palavra da mesma transcricao corrigida. "
            "Nao reinicie, nao resuma, nao acrescente comentarios."
        ),
        max_rounds=4,
    )


def get_legend_max_tokens(transcript: str) -> int:
    return get_legend_profile(transcript).generation_tokens


def generate_legend(transcript: str) -> str:
    return _chat_completion_with_auto_continue(
        action_name="geracao de legenda",
        timeout=180.0,
        model=OPENAI_CAPTION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Organize a legenda por blocos de assunto, sem seguir obrigatoriamente a ordem cronologica do audio. "
                    "Priorize limpeza visual e economia de texto, mas nao corte conclusoes ou ressalvas que mudam a ideia.\n\n"
                    f"{get_legend_budget_instruction(transcript)}\n\n"
                    f"Transcricao do audio:\n\n{transcript}"
                )
            }
        ],
        temperature=0.4,
        max_tokens=get_legend_max_tokens(transcript),
        continue_instruction=(
            "Continue exatamente do ponto em que parou. "
            "Nao reinicie a legenda, nao repita trechos ja escritos e mantenha o mesmo HTML."
        ),
    )


def compact_legend_if_needed(transcript: str, legend: str) -> str:
    profile = get_legend_profile(transcript)

    if not legend_needs_compaction(legend, transcript):
        return legend

    logger.info("Legenda acima do tamanho alvo. Rodando compactacao (%s chars).", len(legend))

    compacted = _chat_completion_with_auto_continue(
        action_name="compactacao de legenda",
        timeout=120.0,
        model=OPENAI_CAPTION_MODEL,
        messages=[
            {"role": "system", "content": LEGEND_COMPACTION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{get_legend_budget_instruction(transcript)}\n\n"
                    f"Transcricao corrigida:\n\n{transcript}\n\n"
                    f"Legenda atual:\n\n{legend}"
                )
            }
        ],
        temperature=0.3,
        max_tokens=profile.compaction_tokens,
        continue_instruction=(
            "Continue exatamente do ponto em que parou. "
            "Nao reinicie, nao repita e devolva somente o restante da mesma legenda em HTML."
        ),
        max_rounds=2,
    )
    compacted = strip_model_wrappers(compacted)
    original_plain = _strip_html_tags(legend).strip()
    compacted_plain = _strip_html_tags(compacted).strip()

    if not compacted_plain:
        logger.warning("Compactacao retornou vazia. Mantendo legenda original.")
        return legend

    if len(compacted_plain) < profile.min_plain_chars and len(original_plain) > profile.min_plain_chars:
        logger.warning(
            "Compactacao encolheu demais a legenda (%s -> %s chars). Mantendo legenda original.",
            len(original_plain),
            len(compacted_plain),
        )
        return legend

    if len(compacted_plain) >= int(len(original_plain) * 0.97):
        logger.info("Compactacao nao reduziu a legenda de forma util. Mantendo original.")
        return legend

    logger.info("Legenda compactada (%s -> %s chars).", len(original_plain), len(compacted_plain))
    return compacted


def enforce_entity_fidelity(transcript: str, legend: str) -> str:
    last_legend = _chat_completion_with_auto_continue(
        action_name="revisao final de nomes",
        timeout=120.0,
        model=OPENAI_NAMES_MODEL,
        messages=[
            {"role": "system", "content": ENTITY_FIDELITY_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Transcricao corrigida:\n\n{transcript}\n\n"
                    f"Legenda gerada:\n\n{legend}"
                )
            }
        ],
        temperature=0,
        max_tokens=max(int(len(legend.split()) * 2.6), 420),
        continue_instruction=(
            "Continue exatamente do ponto em que parou. "
            "Nao reinicie, nao repita e devolva somente o restante da mesma legenda em HTML."
        ),
    )

    if len(last_legend.strip()) < int(len(legend.strip()) * 0.7):
        logger.warning(
            "Revisão final encolheu demais a legenda (%s -> %s chars). Mantendo legenda original.",
            len(legend),
            len(last_legend),
        )
        return legend

    return last_legend


# ── Handlers do Telegram ──────────────────────────────────────────────────────

async def _telegram_call_with_retry(coro_factory, *, action_name: str, attempts: int = 3):
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except TimedOut:
            if attempt >= attempts:
                raise
            delay = min(2 ** (attempt - 1), 8)
            logger.warning(
                "%s expirou no Telegram (tentativa %s/%s). Nova tentativa em %.1fs.",
                action_name,
                attempt,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)


async def process_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Mensagem recebida de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return

    try:
        processing_msg = await update.message.reply_text("⏳ Processando áudio...")

        if update.message.voice:
            audio_source = update.message.voice
            tg_file = await _telegram_call_with_retry(
                audio_source.get_file, action_name="Obter arquivo (voice)"
            )
            filename = _safe_audio_filename(None, audio_source.mime_type, "voice.ogg")
            mime_type = _audio_mime_type(filename, audio_source.mime_type)
            duration_seconds = audio_source.duration
            declared_file_size = audio_source.file_size
            source_kind = "voice"
        elif update.message.audio:
            audio_source = update.message.audio
            tg_file = await _telegram_call_with_retry(
                audio_source.get_file, action_name="Obter arquivo (audio)"
            )
            filename = _safe_audio_filename(audio_source.file_name, audio_source.mime_type, "audio.ogg")
            mime_type = _audio_mime_type(filename, audio_source.mime_type)
            duration_seconds = audio_source.duration
            declared_file_size = audio_source.file_size
            source_kind = "audio"
        else:
            return

        logger.info(
            "Metadados do áudio Telegram | tipo=%s filename=%s mime=%s tamanho_declarado=%s duração=%ss",
            source_kind,
            filename,
            mime_type,
            declared_file_size,
            duration_seconds,
        )
        _ensure_audio_size_is_supported(declared_file_size)

        audio_bytes = await _telegram_call_with_retry(
            tg_file.download_as_bytearray, action_name="Download do áudio"
        )
        _ensure_audio_size_is_supported(len(audio_bytes))
        logger.info(
            "Áudio recebido: %s bytes | filename=%s | mime=%s | duração=%ss",
            len(audio_bytes),
            filename,
            mime_type,
            duration_seconds,
        )

        await processing_msg.edit_text("🎙️ Transcrevendo com Whisper...")
        transcript = await asyncio.to_thread(
            transcribe_audio,
            bytes(audio_bytes),
            filename,
            duration_seconds,
            mime_type,
        )
        logger.info(f"Transcrição ({len(transcript)} chars)")

        await processing_msg.edit_text("🧠 Corrigindo nomes...")
        corrected_transcript = await asyncio.to_thread(correct_player_names, transcript)
        logger.info(f"Transcrição corrigida ({len(corrected_transcript)} chars)")

        await processing_msg.edit_text("✍️ Gerando legenda...")
        legend = await asyncio.to_thread(generate_legend, corrected_transcript)
        logger.info(f"Legenda gerada ({len(legend)} chars)")
        legend = strip_model_wrappers(legend)
        logger.info(f"Legenda sem wrappers apos geracao ({len(legend)} chars)")
        legend = await asyncio.to_thread(compact_legend_if_needed, corrected_transcript, legend)
        logger.info(f"Legenda apos checagem de tamanho ({len(legend)} chars)")
        await processing_msg.edit_text("🔎 Revisando nomes e fidelidade...")
        legend = await asyncio.to_thread(enforce_entity_fidelity, corrected_transcript, legend)
        logger.info(f"Legenda revisada ({len(legend)} chars)")
        legend = strip_model_wrappers(legend)
        logger.info(f"Legenda sem wrappers de markdown ({len(legend)} chars)")
        legend = sanitize_telegram_html(legend)
        legend = force_main_title_uppercase(legend)
        legend = reduce_excess_line_emojis(legend)
        logger.info(f"Legenda sanitizada para HTML Telegram ({len(legend)} chars)")

        await processing_msg.edit_text(legend, parse_mode='HTML')
        logger.info("✅ Legenda enviada com sucesso.")

    except UserFacingError as e:
        logger.warning(f"Erro tratado para usuário: {e}")
        await update.message.reply_text(str(e))
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro OpenAI: {e.response.status_code} - {e.response.text}")
        await update.message.reply_text(
            f"❌ Erro na API OpenAI (código {e.response.status_code})."
        )
    except TimedOut as e:
        logger.error(f"Timeout de rede com o Telegram: {e}")
        await update.message.reply_text(
            "❌ A conexão com o Telegram expirou mesmo após novas tentativas. "
            "Tente reenviar o áudio em instantes."
        )
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return
    await update.message.reply_text(
        "🎙️ Bot de Legendagem TCC ativo!\n\nEnvie um áudio e aguarde a legenda."
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

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(30.0)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, process_audio_message))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    logger.info("Bot rodando... aguardando mensagens.")
    await asyncio.Event().wait()


if __name__ == '__main__':
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    asyncio.run(run_bot())
