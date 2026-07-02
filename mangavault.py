"""
MangaVault Bot — Bot unificado para MangaAI Pro + NEON VAULT
╔═══════════════════════════════════════════════════════╗
║  🌴 Edición: Cyberpunk Miami Vice Criminal Pack       ║
╚═══════════════════════════════════════════════════════╝
Funciones:
  /start    → bienvenida + menú
  /manga    → genera imagen con FLUX vía Pollinations.ai
  /arcade   → trivia retro gaming + link a NEON VAULT
  /invite   → link de referido único con contador
  /top      → ranking de referidos
  /web      → links directos a las páginas
  /premium  → comprar imágenes extra con Telegram Stars ⭐
  /stats    → estadísticas del bot (solo admin)
  /misimg   → cuántas imágenes te quedan hoy
  /gta6     → 🔥 Últimas noticias de GTA VI (estilo Vice City)
  /vice     → genera imagen estilo Cyberpunk Miami Vice

Novedades v3 — Miami Vice Criminal Edition:
  - /gta6: scraper de noticias GTA VI vía RSS (Kotaku/IGN/RockstarMag)
    con formateo estilo Vice City criminal
  - /vice: generador de imágenes temático Miami Vice cyberpunk
  - Trivia extendida con preguntas de GTA
  - Easter eggs de Vice City en mensajes del bot
"""

import logging
import asyncio
import aiohttp
import sqlite3
import json
import os
import time
import random
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont


from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    filters, ContextTypes
)

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────#
# Carga desde variables de entorno. En kawai, setea antes de correr:
#   export MANGAVAULT_TOKEN="tu_token_de_botfather"
#   export MANGAVAULT_ADMIN_ID="tu_user_id_de_telegram"
# O agrégalas en el .service de systemd:
#   Environment="MANGAVAULT_TOKEN=..."
#   Environment="MANGAVAULT_ADMIN_ID=..."
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
TELEGRAM_TOKEN = os.getenv("MANGAVAULT_TOKEN", "")
ADMIN_ID       = int(os.getenv("MANGAVAULT_ADMIN_ID", "0"))
MODEL_NAME     = os.getenv("OLLAMA_MODEL", "qwen3:4b")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ MANGAVAULT_TOKEN no está seteado. Exporta la variable antes de correr el bot.")
if ADMIN_ID == 0:
    logging.warning("⚠️  MANGAVAULT_ADMIN_ID no seteado — /stats estará deshabilitado.")

URL_MANGA  = "https://ferplex.github.io/mangaai-pro/"
URL_ARCADE = "https://ferplex.github.io/neon-v/"
URL_BLOG   = "https://nautiluslaarhc.blogspot.com/"

DAILY_LIMIT = 3          # imágenes gratis por día
DB_FILE     = "mangavault.db"

# Packs de Telegram Stars (1 Star ≈ $0.013 USD aprox)
PACKS_STARS = [
    {"id": "pack_5",  "label": "Pack Básico",   "stars": 50,  "imagenes": 5,  "emoji": "⭐"},
    {"id": "pack_15", "label": "Pack Pro",      "stars": 120, "imagenes": 15, "emoji": "🌟"},
    {"id": "pack_40", "label": "Pack Ultimate", "stars": 250, "imagenes": 40, "emoji": "💫"},
]

# ─── ESTILOS ──────────────────────────────────────────────────────────────────
# Gratis
ESTILOS_FREE = {
    "manga":      ("📖 Manga",       "manga style, black and white, detailed linework"),
    "anime":      ("✨ Anime",       "anime style, vibrant colors, cel shaded"),
    "watercolor": ("🎨 Acuarela",    "watercolor painting style, soft colors, artistic"),
    "cel":        ("🖼️ Cel",         "cel animation style, flat colors, clean lines"),
    "realistic":  ("📷 Realista",    "photorealistic, highly detailed, 8k quality"),
    "chibi":      ("🐱 Chibi",       "chibi style, cute, super deformed, kawaii"),
    "mecha":      ("🤖 Mecha",       "mecha style, robots, mechanical details, sci-fi"),
    "fantasy":    ("🧙 Fantasía",    "fantasy art style, magical, epic, detailed"),
    "sketch":     ("✏️ Boceto",      "pencil sketch, rough lines, artistic, monochrome"),
    "voxel":      ("🧱 Voxel",       "voxel art style, 3D colored cubes, isometric view, Minecraft aesthetic"),
    "pixel8":     ("👾 Pixel 8-bit", "8-bit pixel art, retro video game sprite, NES SNES style"),
    "cyberpunk":  ("🌆 Cyberpunk",   "cyberpunk city, neon lights, futuristic, rain, neon signs"),
}

# Premium (solo con Stars)
ESTILOS_PREMIUM = {
    "noir":   ("🎞️ Noir ⭐",    "film noir style, black and white photography, dramatic shadows, 1940s aesthetic, cinematic"),
    "ghibli": ("🌿 Ghibli ⭐",  "Studio Ghibli animation style, soft watercolor, lush backgrounds, whimsical, Miyazaki"),
    "niji":   ("🌈 Niji ⭐",    "niji style, anime illustration, vibrant colors, Japanese art, detailed character design"),
    "lofi":   ("🎵 Lo-fi ⭐",   "lo-fi aesthetic, cozy, soft pastel colors, rainy window, chill anime art"),
    "ukiyo":  ("🌊 Ukiyo-e ⭐", "ukiyo-e woodblock print style, Japanese traditional art, bold outlines, flat colors, Hokusai"),
}

ESTILOS = {**ESTILOS_FREE, **ESTILOS_PREMIUM}

# ─── ESTILOS VICE / MIAMI CRIMINAL (para /vice) ───────────────────────────────
VICE_PROMPTS = [
    "modern gangster in white linen suit with cybernetic arm, Miami Vice neon, nightclub background",
    "neon samurai with katana wearing Miami Vice blazer, hot pink and cyan neon, tropical city",
    "cyber cartel boss with holographic sunglasses, neon Miami skyline, art deco building",
    "female assassin in neon pink cyberpunk Vice City outfit, palm trees, night rain",
    "futuristic hitman in white suit with plasma pistol, Miami beach neon reflection",
    "cyber yakuza underboss with glowing katana and trench coat, vice city alley",
    "hacker gangster with AR visor and tropical shirt, neon bar Miami",
    "cyber detective noir in 80s neon trench coat, Miami rain reflections",
    "mafia enforcer with mechanical fist, neon cigar, art deco hotel background",
    "street crime lord with neon tattoos and gold chains, nightclub entrance Vice City",
]

VICE_ESTILOS_IA = [
    "cyberpunk Miami Vice aesthetic, neon pink and cyan, synthwave 80s, high detail",
    "neon noir criminal art, hot pink electric blue, tropical cyberpunk, sharp",
    "retrofuturistic Vice City style, gold chrome neon, art deco, cinematic",
    "synthwave criminal underworld, neon palm trees, holographic lights, dramatic",
]

# ─── FUENTES RSS — NOTICIAS GTA 6 ────────────────────────────────────────────
GTA6_RSS_FEEDS = [
    # Feed, nombre del medio, emoji
    ("https://kotaku.com/rss/tag/gta-6", "Kotaku", "🎮"),
    ("https://www.ign.com/rss/articles/news", "IGN", "🔥"),
    ("https://www.pcgamer.com/rss/", "PC Gamer", "💻"),
    ("https://www.eurogamer.net/?format=rss", "Eurogamer", "🌍"),
    ("https://feeds.feedburner.com/gamespot/news", "GameSpot", "📰"),
]

GTA6_KEYWORDS = [
    "gta 6", "gta vi", "grand theft auto 6", "grand theft auto vi",
    "rockstar games", "vice city 2025", "vice city 2026",
]

QUICK_PROMPTS = [
    "cherry blossoms, japanese garden, beautiful anime girl",
    "samurai warrior, traditional armor, katana, dramatic pose",
    "cyberpunk city, neon lights, futuristic, rain",
    "majestic dragon, epic fantasy, detailed scales",
    "magical girl, glowing staff, sparkles, transformation",
]

# ─── TRIVIA ───────────────────────────────────────────────────────────────────
TRIVIA_PREGUNTAS = [
    {"pregunta": "¿En qué año salió el primer Street Fighter?",
     "opciones": ["1985", "1987", "1991", "1994"], "correcto": 1,
     "extra": "Street Fighter original fue en 1987. Street Fighter II (1991) fue el que lo hizo famoso."},
    {"pregunta": "¿Cuál era el nombre del dinosaurio de Super Mario World?",
     "opciones": ["Yoshi", "Rex", "Dino", "Koopa"], "correcto": 0,
     "extra": "¡Yoshi! Debutó en Super Mario World de SNES en 1990."},
    {"pregunta": "¿Cuántas vidas tenía Pac-Man al inicio?",
     "opciones": ["2", "3", "4", "5"], "correcto": 1,
     "extra": "3 vidas. El fantasma rojo (Blinky) era el más agresivo."},
    {"pregunta": "¿De qué consola fue exclusivo GoldenEye 007?",
     "opciones": ["PlayStation", "Sega Saturn", "Nintendo 64", "Game Boy"], "correcto": 2,
     "extra": "Nintendo 64, 1997. Uno de los mejores shooters de la historia."},
    {"pregunta": "¿Cómo se llama el villano principal de The Legend of Zelda?",
     "opciones": ["Bowser", "Ganondorf", "Dedede", "Eggman"], "correcto": 1,
     "extra": "Ganondorf / Ganon. La triforce del poder es suya."},
    {"pregunta": "¿En qué año se lanzó el primer Game Boy?",
     "opciones": ["1985", "1987", "1989", "1992"], "correcto": 2,
     "extra": "1989 en Japón. Tetris fue su juego estrella de lanzamiento."},
    {"pregunta": "¿Qué consola usaba cartuchos de 16 bits y tenía el Sonic original?",
     "opciones": ["SNES", "Sega Genesis / Mega Drive", "Atari 2600", "Neo Geo"], "correcto": 1,
     "extra": "Sega Genesis (Mega Drive fuera de América), 1988-1994."},
    {"pregunta": "¿Cuántos Chaos Emeralds hay en Sonic the Hedgehog?",
     "opciones": ["5", "6", "7", "8"], "correcto": 2,
     "extra": "7 Chaos Emeralds para conseguir a Super Sonic. ¡Clásico!"},
    {"pregunta": "¿Qué personaje NO es de Nintendo?",
     "opciones": ["Mario", "Pikachu", "Sonic", "Kirby"], "correcto": 2,
     "extra": "Sonic es de Sega. Mario, Pikachu y Kirby son de Nintendo."},
    {"pregunta": "¿En qué ciudad ficticia transcurre GTA: Vice City?",
     "opciones": ["Liberty City", "San Andreas", "Vice City", "Los Santos"], "correcto": 2,
     "extra": "Vice City está basada en Miami de los 80s. Soundtrack épico de synthwave. 🌴"},
    {"pregunta": "¿En qué año se lanzó GTA: Vice City?",
     "opciones": ["2001", "2002", "2003", "2004"], "correcto": 1,
     "extra": "2002 en PS2. Tommy Vercetti vs los Forelli. Clásico absoluto."},
    {"pregunta": "¿Cómo se llama el protagonista de GTA: Vice City?",
     "opciones": ["Carl Johnson", "Tommy Vercetti", "Niko Bellic", "Trevor Phillips"], "correcto": 1,
     "extra": "Tommy Vercetti, expresidiario mandado por Sonny Forelli a Vice City. 🔫"},
    {"pregunta": "¿Qué ciudad inspira el mapa de GTA V / Los Santos?",
     "opciones": ["New York", "Miami", "Los Ángeles", "Las Vegas"], "correcto": 2,
     "extra": "Los Santos = Los Ángeles. Con Vinewood = Hollywood. GTA V salió en 2013."},
    {"pregunta": "¿Cuántos protagonistas jugables tiene GTA V?",
     "opciones": ["1", "2", "3", "4"], "correcto": 2,
     "extra": "3 protagonistas: Michael, Trevor y Franklin. Innovación de la saga."},
]

# ─── BASE DE DATOS SQLite ─────────────────────────────────────────────────────
def init_db() -> None:
    """Inicializa la base de datos y crea tablas si no existen."""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id         INTEGER PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            imagenes_hoy    INTEGER DEFAULT 0,
            ultimo_reset    REAL    DEFAULT 0,
            referidos_count INTEGER DEFAULT 0,
            bonus_imagenes  INTEGER DEFAULT 0,
            stars_imagenes  INTEGER DEFAULT 0,
            trivia_correctas INTEGER DEFAULT 0,
            total_generadas INTEGER DEFAULT 0,
            fecha_registro  TEXT    DEFAULT (datetime('now')),
            referido_por    INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS compras_stars (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            pack_id     TEXT,
            stars       INTEGER,
            imagenes    INTEGER,
            fecha       TEXT DEFAULT (datetime('now')),
            payload     TEXT
        );
        CREATE TABLE IF NOT EXISTS log_generaciones (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            estilo    TEXT,
            prompt    TEXT,
            fecha     TEXT DEFAULT (datetime('now'))
        );
    """)
    con.commit()
    con.close()

def db_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

def get_usuario(user_id: int, username: str = "", first_name: str = "") -> sqlite3.Row:
    """Obtiene o crea el usuario. Resetea contador diario si pasaron 24h."""
    con = db_con()
    cur = con.cursor()
    cur.execute("SELECT * FROM usuarios WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO usuarios (user_id, username, first_name) VALUES (?,?,?)",
            (user_id, username, first_name)
        )
        con.commit()
        cur.execute("SELECT * FROM usuarios WHERE user_id=?", (user_id,))
        row = cur.fetchone()
    # Resetear si pasaron >24h
    if time.time() - row["ultimo_reset"] > 86400:
        cur.execute(
            "UPDATE usuarios SET imagenes_hoy=0, ultimo_reset=? WHERE user_id=?",
            (time.time(), user_id)
        )
        con.commit()
        cur.execute("SELECT * FROM usuarios WHERE user_id=?", (user_id,))
        row = cur.fetchone()
    con.close()
    return row

def actualizar_campo(user_id: int, campo: str, valor) -> None:
    con = db_con()
    con.execute(f"UPDATE usuarios SET {campo}=? WHERE user_id=?", (valor, user_id))
    con.commit()
    con.close()

def incrementar(user_id: int, campo: str, delta: int = 1) -> None:
    con = db_con()
    con.execute(f"UPDATE usuarios SET {campo}={campo}+? WHERE user_id=?", (delta, user_id))
    con.commit()
    con.close()

def registrar_generacion(user_id: int, estilo: str, prompt: str) -> None:
    con = db_con()
    con.execute(
        "INSERT INTO log_generaciones (user_id, estilo, prompt) VALUES (?,?,?)",
        (user_id, estilo, prompt[:200])
    )
    con.commit()
    con.close()

def registrar_compra(user_id: int, pack_id: str, stars: int, imagenes: int, payload: str) -> None:
    con = db_con()
    con.execute(
        "INSERT INTO compras_stars (user_id, pack_id, stars, imagenes, payload) VALUES (?,?,?,?,?)",
        (user_id, pack_id, stars, imagenes, payload)
    )
    con.execute(
        "UPDATE usuarios SET stars_imagenes=stars_imagenes+? WHERE user_id=?",
        (imagenes, user_id)
    )
    con.commit()
    con.close()

def usar_imagen(user_id: int) -> None:
    """Descuenta una imagen del cupo diario y suma al total generado."""
    con = db_con()
    con.execute(
        "UPDATE usuarios SET imagenes_hoy=imagenes_hoy+1, total_generadas=total_generadas+1 WHERE user_id=?",
        (user_id,)
    )
    con.commit()
    con.close()

# ─── OLLAMA ───────────────────────────────────────────────────────────────────
async def mejorar_prompt_ollama(prompt_es: str) -> str:
    sistema = (
        "You are a prompt engineer for image generation with FLUX. "
        "The user sends a description in Spanish. "
        "Translate it to English and enhance it for manga/anime art style. "
        "Add: high quality, detailed linework, manga style, dramatic lighting. "
        "Keep it under 80 words. Reply ONLY with the enhanced English prompt, nothing else."
    )
    payload = {
        "model": MODEL_NAME,
        "prompt": f"{sistema}\n\nUsuario: {prompt_es}\nPrompt mejorado:",
        "stream": False,
    }
    timeout = aiohttp.ClientTimeout(total=120)   # 120s pa aguantar carga del modelo
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", prompt_es).strip()
    except Exception:
        pass
    return f"manga style, anime art, {prompt_es}, high quality, detailed"

# ─── MARCA DE AGUA ────────────────────────────────────────────────────────────
def agregar_marca_agua(img_bytes: bytes) -> bytes:
    """Dibuja '© NAUTILUS LAB — nautlab.itch.io' en la esquina inferior de la imagen."""
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        texto = "© NAUTILUS LAB — nautlab.itch.io"
        font_size = max(14, round(img.width * 0.022))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        padding = font_size * 0.9

        # barra semitransparente de fondo para legibilidad
        bar_h = text_h + padding * 1.2
        draw.rectangle(
            [(0, img.height - bar_h), (text_w + padding * 2, img.height)],
            fill=(6, 7, 15, 140)
        )
        # tick cyan de acento
        draw.rectangle(
            [(padding * 0.35, img.height - bar_h + padding * 0.25),
             (padding * 0.35 + 3, img.height - padding * 0.35)],
            fill=(0, 229, 204, 230)
        )
        # texto
        draw.text(
            (padding, img.height - bar_h + (bar_h - text_h) / 2 - bbox[1]),
            texto, font=font, fill=(238, 240, 248, 235)
        )

        marcada = Image.alpha_composite(img, overlay).convert("RGB")
        buf = BytesIO()
        marcada.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logging.warning(f"⚠️  No se pudo aplicar marca de agua: {e} — se envía imagen original")
        return img_bytes



async def generar_imagen_flux(prompt_en: str) -> bytes | None:
    """Genera la imagen vía Pollinations, descarga los bytes y le aplica la marca de agua."""
    seed = random.randint(1, 999999)
    prompt_encoded = quote(prompt_en)
    url = (
        f"https://image.pollinations.ai/prompt/{prompt_encoded}"
        f"?model=flux&width=1024&height=1024&seed={seed}&nologo=true"
    )
    timeout = aiohttp.ClientTimeout(total=90)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200 and "image" in resp.headers.get("Content-Type", ""):
                    img_bytes = await resp.read()
                    return agregar_marca_agua(img_bytes)
    except Exception:
        pass
    return None

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def limite_total(u: sqlite3.Row) -> int:
    return DAILY_LIMIT + u["bonus_imagenes"] + u["stars_imagenes"]

def imagenes_disponibles(u: sqlite3.Row) -> int:
    return max(0, limite_total(u) - u["imagenes_hoy"])

# ─── HANDLERS ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u = get_usuario(user.id, user.username or "", user.first_name or "")

    # Registrar referido
    if context.args:
        ref_id_str = context.args[0]
        try:
            ref_id = int(ref_id_str)
        except ValueError:
            ref_id = None
        if ref_id and ref_id != user.id:
            con = db_con()
            ya = con.execute("SELECT referido_por FROM usuarios WHERE user_id=?", (user.id,)).fetchone()
            con.close()
            if ya and ya["referido_por"] is None:
                actualizar_campo(user.id, "referido_por", ref_id)
                incrementar(ref_id, "referidos_count")
                # Bonus por cada 3 referidos
                ref_u = get_usuario(ref_id)
                if ref_u["referidos_count"] % 3 == 0:
                    incrementar(ref_id, "bonus_imagenes")

    nombre = user.first_name or "gamer"
    texto = (
        f"⚡ *¡Bienvenido al MangaVault Bot, {nombre}!*\n\n"
        f"🎨 Genera imágenes manga con IA\n"
        f"🕹️ Juega trivia retro y gana créditos\n"
        f"⭐ Compra packs con Telegram Stars\n"
        f"🔗 Invita amigos y desbloquea más imágenes\n\n"
        f"*Comandos:*\n"
        f"`/manga [desc] | [estilo]` — Genera imagen 🎨\n"
        f"`/arcade` — Trivia retro gaming 🕹️\n"
        f"`/premium` — Packs con Stars ⭐\n"
        f"`/misimg` — Cuántas imágenes te quedan 📊\n"
        f"`/invite` — Tu link viral 🔗\n"
        f"`/top` — Ranking de referidos 🏆\n"
        f"`/creditos` — Puntos de arcade → imágenes ⚡\n"
        f"`/web` — Links a las páginas 🌐"
    )
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎨 MangaAI Pro", url=URL_MANGA),
            InlineKeyboardButton("🕹️ NEON VAULT",  url=f"{URL_ARCADE}?uid={user.id}"),
        ],
        [InlineKeyboardButton("⭐ Ver packs premium", callback_data="ver_premium")],
    ])
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=teclado)


async def cmd_misimg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra cuántas imágenes quedan hoy."""
    user = update.effective_user
    u = get_usuario(user.id, user.username or "", user.first_name or "")
    disp = imagenes_disponibles(u)
    lim  = limite_total(u)
    texto = (
        f"📊 *Tu cuota de imágenes*\n\n"
        f"🎨 Disponibles hoy: *{disp}/{lim}*\n"
        f"  • Gratis base: {DAILY_LIMIT}\n"
        f"  • Bonus referidos: {u['bonus_imagenes']}\n"
        f"  • Stars compradas: {u['stars_imagenes']}\n\n"
        f"📸 Total generadas: *{u['total_generadas']}*\n"
        f"🏆 Trivia correctas: *{u['trivia_correctas']}*\n\n"
    )
    if disp == 0:
        texto += "⚠️ Sin imágenes hoy — usa /premium para comprar más ⭐"
    else:
        texto += f"✅ Puedes generar {disp} imagen(es) más hoy"
    await update.message.reply_text(texto, parse_mode="Markdown")


# ─── MANGA ────────────────────────────────────────────────────────────────────
async def cmd_manga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u    = get_usuario(user.id, user.username or "", user.first_name or "")

    # Verificar cuota
    if u["imagenes_hoy"] >= limite_total(u):
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Comprar pack con Stars", callback_data="ver_premium")],
            [InlineKeyboardButton("🕹️ Ganar créditos en NEON VAULT", url=URL_ARCADE)],
            [InlineKeyboardButton("🔗 Invitar amigos (3 = +1 img/día)", callback_data="invite")],
        ])
        lim = limite_total(u)
        await update.message.reply_text(
            f"⚠️ *Usaste tus {lim} imágenes de hoy.*\n\n"
            f"Para conseguir más:\n"
            f"⭐ Compra un pack con Telegram Stars (`/premium`)\n"
            f"🔗 Invita 3 amigos con `/invite` → +1 img/día\n"
            f"🕹️ 10 trivias correctas → +1 img\n"
            f"🔄 Pack gratis se renueva en 24 horas",
            parse_mode="Markdown",
            reply_markup=teclado
        )
        return

    # Sin argumentos → ayuda
    if not context.args:
        libres  = " | ".join([f"`{k}`" for k in ESTILOS_FREE.keys()])
        premium = " | ".join([f"`{k}`" for k in ESTILOS_PREMIUM.keys()])
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎨 Ver en MangaAI Pro", url=URL_MANGA)],
            [InlineKeyboardButton("⭐ Desbloquear estilos premium", callback_data="ver_premium")],
        ])
        await update.message.reply_text(
            "🎨 *¿Cómo usar /manga?*\n\n"
            "`/manga [descripción] | [estilo]`\n\n"
            "*Ejemplos:*\n"
            "`/manga chica con katana en la lluvia`\n"
            "`/manga dragón cibernético | mecha`\n"
            "`/manga aldea ninja al atardecer | pixel8`\n"
            "`/manga samurai en niebla | noir` ⭐\n\n"
            f"*Estilos gratis:*\n{libres}\n\n"
            f"*Estilos premium ⭐:*\n{premium}",
            parse_mode="Markdown",
            reply_markup=teclado
        )
        return

    texto_completo = " ".join(context.args)
    partes    = texto_completo.split("|")
    prompt_es = partes[0].strip()
    estilo_key = partes[1].strip().lower() if len(partes) > 1 else "manga"

    if estilo_key not in ESTILOS:
        estilo_key = "manga"

    # Bloquear estilos premium si no tiene Stars disponibles
    if estilo_key in ESTILOS_PREMIUM and u["stars_imagenes"] == 0:
        await update.message.reply_text(
            f"⭐ *El estilo `{estilo_key}` es premium.*\n\n"
            f"Compra un pack con Telegram Stars para desbloquearlo.\n"
            f"Usa `/premium` para ver opciones.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Ver packs", callback_data="ver_premium")]
            ])
        )
        return

    estilo_emoji, estilo_prompt = ESTILOS[estilo_key]

    msg = await update.message.reply_text(
        f"⚙️ *Mejorando tu prompt con IA...*\nEstilo: {estilo_emoji}",
        parse_mode="Markdown"
    )

    prompt_base = await mejorar_prompt_ollama(prompt_es)
    prompt_en   = f"{prompt_base}, {estilo_prompt}, masterpiece, best quality, ultra detailed"

    await msg.edit_text(
        f"{estilo_emoji} *Generando con FLUX...*\n\n"
        f"📝 `{prompt_base[:70]}...`",
        parse_mode="Markdown"
    )

    img_bytes = await generar_imagen_flux(prompt_en)

    if img_bytes:
        # Descontar imagen
        incrementar(user.id, "imagenes_hoy")
        incrementar(user.id, "total_generadas")
        # Si usó estilo premium, descontar de stars_imagenes
        if estilo_key in ESTILOS_PREMIUM:
            incrementar(user.id, "stars_imagenes", -1)
        registrar_generacion(user.id, estilo_key, prompt_es)

        u2 = get_usuario(user.id)
        restantes = imagenes_disponibles(u2)
        bot_user  = (await context.bot.get_me()).username
        caption = (
            f"{estilo_emoji} *{prompt_es}*\n\n"
            f"Imágenes restantes hoy: *{restantes}/{limite_total(u2)}*\n"
            f"🤖 @{bot_user} | [MangaAI Pro]({URL_MANGA})"
        )
        await msg.delete()
        await update.message.reply_photo(
            photo=BytesIO(img_bytes),
            caption=caption,
            parse_mode="Markdown"
        )
    else:
        await msg.edit_text(
            "❌ FLUX tardó demasiado en responder.\n\n"
            f"Intenta de nuevo o usa la web:\n{URL_MANGA}"
        )


# ─── PREMIUM / STARS ──────────────────────────────────────────────────────────
async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los packs disponibles con Telegram Stars."""
    texto = (
        "⭐ *MangaVault Premium — Packs con Stars*\n\n"
        "Compra imágenes extra con Telegram Stars.\n"
        "Los Stars también desbloquean estilos exclusivos:\n"
        "`noir` | `ghibli` | `niji` | `lofi` | `ukiyo-e`\n\n"
        "*Elige tu pack:*"
    )
    botones = [
        [InlineKeyboardButton(
            f"{p['emoji']} {p['label']} — {p['imagenes']} imgs — {p['stars']} Stars",
            callback_data=f"comprar_{p['id']}"
        )]
        for p in PACKS_STARS
    ]
    botones.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    await update.message.reply_text(
        texto,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botones)
    )


async def cb_comprar_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia el proceso de pago con Telegram Stars."""
    query = update.callback_query
    await query.answer()

    pack_id = query.data.replace("comprar_", "")
    pack = next((p for p in PACKS_STARS if p["id"] == pack_id), None)
    if not pack:
        await query.edit_message_text("Pack no encontrado.")
        return

    payload = f"{pack_id}:{query.from_user.id}:{int(time.time())}"

    try:
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title=f"MangaVault — {pack['label']}",
            description=(
                f"{pack['imagenes']} imágenes manga extra + acceso a estilos premium\n"
                f"(noir, ghibli, niji, lofi, ukiyo-e)"
            ),
            payload=payload,
            currency="XTR",              # XTR = Telegram Stars
            prices=[LabeledPrice(label=pack["label"], amount=pack["stars"])],
            provider_token="",           # vacío para Stars
        )
        await query.edit_message_text(
            f"⭐ Se abrió el pago para *{pack['label']}* ({pack['stars']} Stars).\n"
            f"Confirma en el mensaje de arriba 👆",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error invoice Stars: {e}")
        await query.edit_message_text(
            "❌ Error al iniciar el pago. Intenta de nuevo en un momento."
        )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validación pre-pago (requerida por Telegram)."""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def pago_exitoso(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acredita las imágenes después del pago exitoso."""
    payment = update.message.successful_payment
    payload = payment.invoice_payload  # "pack_id:user_id:timestamp"
    user    = update.effective_user

    pack_id = payload.split(":")[0]
    pack = next((p for p in PACKS_STARS if p["id"] == pack_id), None)

    if pack:
        registrar_compra(
            user.id, pack_id, payment.total_amount,
            pack["imagenes"], payload
        )
        await update.message.reply_text(
            f"✅ *¡Pago confirmado! {pack['emoji']}*\n\n"
            f"Se acreditaron *{pack['imagenes']} imágenes* a tu cuenta.\n"
            f"Ya puedes usar los estilos premium:\n"
            f"`/manga samurai en niebla | noir`\n"
            f"`/manga bosque mágico | ghibli`\n"
            f"`/manga guerrera | niji`\n\n"
            f"Gracias por apoyar Nautilus Lab 🙏",
            parse_mode="Markdown"
        )
        logging.info(f"Compra Stars: user={user.id} pack={pack_id} imgs={pack['imagenes']}")
    else:
        await update.message.reply_text("✅ Pago recibido. Contacta soporte si no ves tus imágenes.")


# ─── ADMIN STATS ──────────────────────────────────────────────────────────────
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Estadísticas del bot — solo para admin."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Solo para administrador.")
        return

    con = db_con()
    total_users   = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    activos_hoy   = con.execute(
        "SELECT COUNT(*) FROM usuarios WHERE imagenes_hoy > 0"
    ).fetchone()[0]
    total_gen     = con.execute("SELECT SUM(total_generadas) FROM usuarios").fetchone()[0] or 0
    total_refs    = con.execute("SELECT SUM(referidos_count) FROM usuarios").fetchone()[0] or 0
    total_compras = con.execute("SELECT COUNT(*) FROM compras_stars").fetchone()[0]
    stars_total   = con.execute("SELECT SUM(stars) FROM compras_stars").fetchone()[0] or 0
    imgs_vendidas = con.execute("SELECT SUM(imagenes) FROM compras_stars").fetchone()[0] or 0
    top_gen       = con.execute(
        "SELECT user_id, first_name, total_generadas FROM usuarios ORDER BY total_generadas DESC LIMIT 5"
    ).fetchall()
    estilos_pop   = con.execute(
        "SELECT estilo, COUNT(*) as cnt FROM log_generaciones GROUP BY estilo ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    nuevos_7d     = con.execute(
        "SELECT COUNT(*) FROM usuarios WHERE fecha_registro >= datetime('now','-7 days')"
    ).fetchone()[0]
    con.close()

    top_txt = "\n".join([f"  {r['first_name'] or r['user_id']}: {r['total_generadas']}" for r in top_gen]) or "  —"
    est_txt = "\n".join([f"  {r['estilo']}: {r['cnt']}" for r in estilos_pop]) or "  —"

    texto = (
        f"📊 *MangaVault Bot — Stats*\n"
        f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n\n"
        f"👥 Usuarios totales: *{total_users}*\n"
        f"📅 Nuevos últimos 7 días: *{nuevos_7d}*\n"
        f"⚡ Activos hoy: *{activos_hoy}*\n"
        f"🎨 Imágenes generadas (total): *{total_gen}*\n"
        f"🔗 Referidos totales: *{total_refs}*\n\n"
        f"⭐ *Stars / Monetización:*\n"
        f"  Compras realizadas: {total_compras}\n"
        f"  Stars recibidos: {stars_total}\n"
        f"  Imágenes vendidas: {imgs_vendidas}\n\n"
        f"🏆 *Top generadores:*\n{top_txt}\n\n"
        f"🎨 *Estilos más usados:*\n{est_txt}"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


# ─── ARCADE / TRIVIA ─────────────────────────────────────────────────────────
async def cmd_arcade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user    = update.effective_user
    u       = get_usuario(user.id, user.username or "", user.first_name or "")
    pregunta = random.choice(TRIVIA_PREGUNTAS)
    context.user_data["trivia"] = pregunta

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{op}", callback_data=f"trivia_{i}")]
        for i, op in enumerate(pregunta["opciones"])
    ] + [
        [InlineKeyboardButton("🕹️ Ir a NEON VAULT", url=f"{URL_ARCADE}?uid={user.id}")]
    ])

    await update.message.reply_text(
        f"🕹️ *TRIVIA RETRO GAMING*\n\n"
        f"*{pregunta['pregunta']}*\n\n"
        f"✅ Correctas: {u['trivia_correctas']} | 🎮 [NEON VAULT]({URL_ARCADE})",
        parse_mode="Markdown",
        reply_markup=teclado
    )


async def callback_trivia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "invite":
        await query.edit_message_text(
            f"🔗 Tu link de invitación:\n"
            f"`https://t.me/{context.bot.username}?start={query.from_user.id}`\n\n"
            f"Por cada 3 amigos → +1 imagen manga/día 🎁",
            parse_mode="Markdown"
        )
        return

    user     = query.from_user
    u        = get_usuario(user.id, user.username or "", user.first_name or "")
    pregunta = context.user_data.get("trivia")

    if not pregunta:
        await query.edit_message_text("Usa /arcade para una nueva pregunta.")
        return

    idx_respuesta = int(query.data.split("_")[1])
    correcto      = pregunta["correcto"]

    if idx_respuesta == correcto:
        incrementar(user.id, "trivia_correctas")
        u2 = get_usuario(user.id)
        if u2["trivia_correctas"] % 10 == 0:
            incrementar(user.id, "bonus_imagenes")
            bonus_msg = "\n\n🎁 *¡Desbloqueaste +1 imagen extra! (10 correctas)*"
        else:
            falta = 10 - (u2["trivia_correctas"] % 10)
            bonus_msg = f"\n\n⚡ {falta} correctas más → +1 imagen extra"
        texto = (
            f"✅ *¡CORRECTO!* La respuesta es: *{pregunta['opciones'][correcto]}*\n\n"
            f"💡 {pregunta['extra']}"
            f"{bonus_msg}\n\n"
            f"🕹️ [Juega más en NEON VAULT]({URL_ARCADE})"
        )
    else:
        texto = (
            f"❌ *Incorrecto.* La respuesta era: *{pregunta['opciones'][correcto]}*\n\n"
            f"💡 {pregunta['extra']}\n\n"
            f"🕹️ [NEON VAULT]({URL_ARCADE}) — sigue jugando"
        )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Otra pregunta", callback_data="nueva_trivia")],
        [InlineKeyboardButton("🎨 /manga", callback_data="ir_manga"),
         InlineKeyboardButton("🕹️ NEON VAULT", url=URL_ARCADE)],
    ])
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=teclado)


async def callback_general(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "nueva_trivia":
        pregunta = random.choice(TRIVIA_PREGUNTAS)
        context.user_data["trivia"] = pregunta
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{op}", callback_data=f"trivia_{i}")]
            for i, op in enumerate(pregunta["opciones"])
        ] + [[InlineKeyboardButton("🕹️ Ir a NEON VAULT", url=URL_ARCADE)]])
        await query.edit_message_text(
            f"🕹️ *TRIVIA RETRO GAMING*\n\n*{pregunta['pregunta']}*",
            parse_mode="Markdown", reply_markup=teclado
        )

    elif query.data == "ir_manga":
        await query.edit_message_text(
            "🎨 Usa: `/manga [descripción]`\n\nEjemplo: `/manga dragón cyberpunk en la lluvia`",
            parse_mode="Markdown"
        )

    elif query.data == "invite":
        await query.edit_message_text(
            f"🔗 Tu link de invitación:\n"
            f"`https://t.me/{context.bot.username}?start={query.from_user.id}`\n\n"
            f"Por cada 3 amigos → +1 imagen manga/día 🎁",
            parse_mode="Markdown"
        )

    elif query.data == "ver_premium":
        texto = (
            "⭐ *MangaVault Premium — Packs con Stars*\n\n"
            "Compra imágenes extra + estilos exclusivos:\n"
            "`noir` | `ghibli` | `niji` | `lofi` | `ukiyo-e`\n\n"
            "*Elige tu pack:*"
        )
        botones = [
            [InlineKeyboardButton(
                f"{p['emoji']} {p['label']} — {p['imagenes']} imgs — {p['stars']} Stars",
                callback_data=f"comprar_{p['id']}"
            )]
            for p in PACKS_STARS
        ]
        botones.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
        await query.edit_message_text(
            texto, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(botones)
        )

    elif query.data == "cancelar":
        await query.edit_message_text("✅ Cancelado.")

    elif query.data == "ir_vice":
        await query.edit_message_text(
            "🌴 *VICE CITY GENERATOR*\n\n"
            "Usa: `/vice [descripción]`\n\n"
            "Ejemplos:\n"
            "• `/vice gánster con traje blanco y neón rosa`\n"
            "• `/vice samurai moderno en Miami nocturna`\n"
            "• `/vice` — imagen aleatoria del pack criminal 🎲",
            parse_mode="Markdown"
        )

    elif query.data == "ir_gta6":
        await query.edit_message_text(
            "📡 Usa `/gta6` para ver las últimas noticias de GTA VI.\n\n"
            "_Interceptando transmisiones de Vice City..._ 🌴",
            parse_mode="Markdown"
        )

    elif query.data == "refresh_gta6":
        # Re-ejecutar búsqueda de noticias
        noticias = await fetch_gta6_news()
        if not noticias:
            await query.edit_message_text(
                "📡 Sin noticias nuevas en este momento. Rockstar sigue en silencio. 🕵️\n\n"
                "Intenta más tarde con `/gta6`.",
                parse_mode="Markdown"
            )
            return
        lineas = [
            "🌴🔫 *VICE CITY CRIMINAL NETWORK* 🔫🌴",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📡 *ÚLTIMAS NOTICIAS GTA VI* _(actualizado)_",
            f"🕐 `{datetime.now().strftime('%d/%m/%Y %H:%M')}`",
            "━━━━━━━━━━━━━━━━━━━━━━\n",
        ]
        for n in noticias:
            lineas.append(f"{n['emoji']} *[{n['fuente']}]*\n🔹 [{n['titulo']}]({n['link']})\n")
        lineas.append("🏖️ _Welcome to Vice City. Population: secrets._")
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_gta6")],
            [InlineKeyboardButton("🎮 r/GTA6", url="https://www.reddit.com/r/GTA6/"),
             InlineKeyboardButton("📰 Rockstar", url="https://www.rockstargames.com/newswire")],
        ])
        await query.edit_message_text(
            "\n".join(lineas), parse_mode="Markdown",
            reply_markup=teclado, disable_web_page_preview=True
        )

    elif query.data.startswith("comprar_"):
        await cb_comprar_pack(update, context)



# ─── GTA 6 NOTICIAS ───────────────────────────────────────────────────────────

async def fetch_gta6_news() -> list[dict]:
    """
    Busca noticias de GTA 6 en múltiples feeds RSS.
    Retorna lista de dicts: {titulo, link, fuente, emoji, fecha}
    """
    noticias = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MangaVaultBot/3.0)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        for feed_url, fuente, emoji in GTA6_RSS_FEEDS:
            try:
                async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        continue
                    xml_text = await resp.text(errors="replace")
                    root = ET.fromstring(xml_text)

                    # Compatibilidad RSS 2.0 y Atom
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

                    for item in items[:15]:  # revisar solo los 15 más recientes
                        titulo_el = item.find("title") or item.find("atom:title", ns)
                        link_el   = item.find("link")  or item.find("atom:link", ns)
                        fecha_el  = item.find("pubDate") or item.find("atom:published", ns)

                        titulo = titulo_el.text.strip() if titulo_el is not None and titulo_el.text else ""
                        link   = (link_el.text or link_el.get("href", "")).strip() if link_el is not None else ""
                        fecha  = fecha_el.text.strip()[:16] if fecha_el is not None and fecha_el.text else "—"

                        # Filtrar por keywords GTA 6
                        titulo_lower = titulo.lower()
                        if any(kw in titulo_lower for kw in GTA6_KEYWORDS):
                            noticias.append({
                                "titulo": titulo,
                                "link":   link,
                                "fuente": fuente,
                                "emoji":  emoji,
                                "fecha":  fecha,
                            })
            except Exception:
                continue

    # Fallback: búsqueda web simple si no hay RSS
    if not noticias:
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                url = "https://news.google.com/rss/search?q=GTA+6+Rockstar&hl=es&gl=MX&ceid=MX:es"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        xml_text = await resp.text(errors="replace")
                        root = ET.fromstring(xml_text)
                        for item in root.findall(".//item")[:8]:
                            titulo_el = item.find("title")
                            link_el   = item.find("link")
                            fecha_el  = item.find("pubDate")
                            titulo = titulo_el.text.strip() if titulo_el is not None and titulo_el.text else ""
                            link   = link_el.text.strip() if link_el is not None and link_el.text else ""
                            fecha  = fecha_el.text.strip()[:16] if fecha_el is not None and fecha_el.text else "—"
                            if titulo:
                                noticias.append({
                                    "titulo": titulo,
                                    "link":   link,
                                    "fuente": "Google News",
                                    "emoji":  "📡",
                                    "fecha":  fecha,
                                })
        except Exception:
            pass

    return noticias[:6]  # máximo 6 noticias


async def cmd_gta6(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /gta6 — últimas noticias de GTA VI estilo Vice City criminal."""
    msg = await update.message.reply_text(
        "🌴 *INTERCEPTANDO TRANSMISIÓN DE VICE CITY...*\n"
        "📡 Conectando a la red criminal de Rockstar...",
        parse_mode="Markdown"
    )

    noticias = await fetch_gta6_news()

    if not noticias:
        await msg.edit_text(
            "🚔 *VICE CITY INTELLIGENCE — SIN SEÑAL*\n\n"
            "No se encontraron noticias recientes de GTA VI en este momento.\n"
            "Las fuentes están silenciosas... o Rockstar borró las pistas. 🕵️\n\n"
            "🔗 Intenta directamente:\n"
            "• [Rockstar Newswire](https://www.rockstargames.com/newswire)\n"
            "• [r/GTA6](https://www.reddit.com/r/GTA6/)\n"
            "• [GTAForums](https://gtaforums.com/)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return

    # Construir mensaje estilo Vice City
    lineas = [
        "🌴🔫 *VICE CITY CRIMINAL NETWORK* 🔫🌴",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📡 *ÚLTIMAS NOTICIAS GTA VI*",
        f"🕐 Actualizado: `{datetime.now().strftime('%d/%m/%Y %H:%M')}`",
        "━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for i, n in enumerate(noticias, 1):
        lineas.append(
            f"{n['emoji']} *[{n['fuente']}]* — `{n['fecha']}`\n"
            f"🔹 [{n['titulo']}]({n['link']})\n"
        )

    lineas += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🏖️ _Welcome to Vice City. Population: secrets._",
    ]

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualizar noticias", callback_data="refresh_gta6")],
        [InlineKeyboardButton("🎮 r/GTA6", url="https://www.reddit.com/r/GTA6/"),
         InlineKeyboardButton("📰 Rockstar News", url="https://www.rockstargames.com/newswire")],
        [InlineKeyboardButton("🌴 /vice — Genera imagen Vice City", callback_data="ir_vice")],
    ])

    await msg.edit_text(
        "\n".join(lineas),
        parse_mode="Markdown",
        reply_markup=teclado,
        disable_web_page_preview=True
    )


# ─── VICE CITY — GENERADOR DE IMÁGENES MIAMI CRIMINAL ────────────────────────

async def cmd_vice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /vice — genera imagen estilo Cyberpunk Miami Vice."""
    user = update.effective_user
    u = get_usuario(user.id, user.username or "", user.first_name or "")

    # Verificar cuota (comparte límite con /manga)
    imagenes_hoy  = u["imagenes_hoy"]
    bonus         = u["bonus_imagenes"]
    stars_imgs    = u["stars_imagenes"]
    limite_hoy    = DAILY_LIMIT + bonus + stars_imgs

    if imagenes_hoy >= limite_hoy:
        await update.message.reply_text(
            "🌴 *VICE CITY — ACCESO DENEGADO*\n\n"
            f"Ya usaste tus {limite_hoy} imágenes de hoy, criminal.\n"
            "Vuelve mañana o consigue más con `/premium` ⭐\n\n"
            "_Tommy Vercetti nunca se rinde... pero tú sí por hoy._ 😏",
            parse_mode="Markdown"
        )
        return

    args_text = " ".join(context.args).strip() if context.args else ""

    # Si no pasan prompt, elegir uno random del pack Vice
    if not args_text:
        prompt_base = random.choice(VICE_PROMPTS)
        fuente_msg = "🎲 _Prompt Vice City aleatorio — usa `/vice [tu descripción]` para personalizar_"
    else:
        prompt_base = args_text
        fuente_msg = f"✏️ _Tu descripción: {args_text[:60]}_"

    estilo_extra = random.choice(VICE_ESTILOS_IA)
    prompt_final = f"{prompt_base}, {estilo_extra}"

    msg = await update.message.reply_text(
        f"🌴 *VICE CITY GENERATOR* 🔫\n\n"
        f"🎨 Generando tu asset criminal...\n"
        f"{fuente_msg}",
        parse_mode="Markdown"
    )

    # Mejorar prompt con Ollama (igual que /manga)
    prompt_mejorado = prompt_final
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": MODEL_NAME,
                "prompt": (
                    f"Improve this image generation prompt for a cyberpunk Miami Vice criminal art style. "
                    f"Keep it under 80 words, English only, add neon colors and vice city atmosphere. "
                    f"Original: {prompt_final}"
                ),
                "stream": False,
                "options": {"num_predict": 100}
            }
            async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    prompt_mejorado = data.get("response", prompt_final).strip()
    except Exception:
        pass

    # Generar vía Pollinations con seed Miami Vice
    seed = random.randint(1000, 9999)
    url_imagen = (
        f"https://image.pollinations.ai/prompt/{quote(prompt_mejorado)}"
        f"?width=768&height=512&seed={seed}&nologo=true&model=flux"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_imagen, timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status == 200:
                    img_bytes = agregar_marca_agua(await r.read())

                    # Descontar imagen del cupo
                    usar_imagen(user.id)
                    registrar_generacion(user.id, "vice_miami", prompt_mejorado)

                    restantes = limite_hoy - imagenes_hoy - 1
                    caption = (
                        f"🌴 *VICE CITY CRIMINAL ART* 🔫\n\n"
                        f"🎨 `{prompt_base[:60]}...`\n\n"
                        f"📸 Imágenes restantes hoy: *{max(0, restantes)}*\n"
                        f"_Welcome to Vice City. Have a nice day._ 😎"
                    )

                    teclado = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Otra imagen Vice", callback_data="ir_vice"),
                         InlineKeyboardButton("📰 /gta6 noticias", callback_data="ir_gta6")],
                        [InlineKeyboardButton("🌆 /manga imagen", callback_data="ir_manga")],
                    ])

                    await msg.delete()
                    await update.message.reply_photo(
                        photo=img_bytes,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=teclado
                    )
                    return

    except Exception as e:
        logging.error(f"Error generando imagen Vice: {e}")

    await msg.edit_text(
        "⚠️ *Vice City Generator offline*\n\n"
        "No se pudo conectar con Pollinations.ai.\n"
        "Intenta de nuevo en un momento, criminal. 🌴",
        parse_mode="Markdown"
    )


# ─── REFERIDOS ────────────────────────────────────────────────────────────────
async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u    = get_usuario(user.id, user.username or "", user.first_name or "")

    bot_username = context.bot.username
    link  = f"https://t.me/{bot_username}?start={user.id}"
    refs  = u["referidos_count"]
    falta = 3 - (refs % 3) if refs % 3 != 0 else 3

    await update.message.reply_text(
        f"🔗 *Tu link de invitación:*\n"
        f"`{link}`\n\n"
        f"📊 Amigos invitados: *{refs}*\n"
        f"🎁 Próximo bonus en: *{falta}* invitado(s)\n\n"
        f"*¿Cómo funciona?*\n"
        f"• Cada 3 amigos con tu link → +1 imagen/día\n"
        f"• Cada 10 trivias correctas → +1 imagen/día\n"
        f"• Sin límite de bonuses acumulables 🚀\n\n"
        f"Comparte en grupos de anime, manga y gaming 👇",
        parse_mode="Markdown"
    )


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    con  = db_con()
    rows = con.execute(
        "SELECT user_id, first_name, referidos_count FROM usuarios "
        "WHERE referidos_count > 0 ORDER BY referidos_count DESC LIMIT 5"
    ).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text(
            "🏆 *TOP REFERIDOS*\n\nAún no hay referidos. ¡Sé el primero con `/invite`!",
            parse_mode="Markdown"
        )
        return

    medallas = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    texto = "🏆 *TOP REFERIDOS*\n\n"
    for i, row in enumerate(rows):
        nombre = row["first_name"] or f"ID···{str(row['user_id'])[-4:]}"
        texto += f"{medallas[i]} *{nombre}* — {row['referidos_count']} referidos\n"
    texto += f"\n🔗 Únete con `/invite` y aparece aquí"
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 MangaAI Pro — Genera imágenes", url=URL_MANGA)],
        [InlineKeyboardButton("🕹️ NEON VAULT — Arcade cyberpunk", url=f"{URL_ARCADE}?uid={user.id}")],
        [InlineKeyboardButton("📝 Blog — Updates & devlogs", url=URL_BLOG)],
    ])
    await update.message.reply_text(
        "🌐 *Nuestras páginas:*\n\n"
        "🎨 *MangaAI Pro* — Genera hasta 3 imágenes manga/día gratis\n"
        "🕹️ *NEON VAULT* — Arcade cyberpunk, gana créditos VC\n"
        "📝 *Blog* — Updates, devlogs y noticias del proyecto\n\n"
        "Los créditos VC de NEON VAULT se usan en MangaAI Pro para más imágenes 🔗\n"
        "Revisa tu saldo con /creditos",
        parse_mode="Markdown",
        reply_markup=teclado
    )


async def cmd_creditos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los puntos de arcade acumulados y las imágenes bonus ganadas."""
    user = update.effective_user
    u = get_usuario(user.id, user.username or "", user.first_name or "")
    con = db_con()
    row = con.execute(
        "SELECT arcade_pts, arcade_bonus_otorgado FROM usuarios WHERE user_id=?", (user.id,)
    ).fetchone()
    con.close()

    pts = (row["arcade_pts"] if row else 0) or 0
    bonus = (row["arcade_bonus_otorgado"] if row else 0) or 0
    faltan = 200 - (pts % 200) if pts % 200 != 0 else 200  # 200 = ARCADE_PTS_POR_IMAGEN

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🕹️ Ir a jugar", url=f"{URL_ARCADE}?uid={user.id}")]
    ])
    await update.message.reply_text(
        f"🕹️ *TUS CRÉDITOS DE ARCADE*\n\n"
        f"⚡ Puntos acumulados: *{pts}*\n"
        f"🎁 Imágenes bonus ganadas: *{bonus}*\n"
        f"📈 Te faltan *{faltan}* pts para la siguiente imagen\n\n"
        f"_Cada 200 puntos en NEON VAULT = +1 imagen bonus._",
        parse_mode="Markdown",
        reply_markup=teclado
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logging.info("🗄️ Base de datos SQLite lista")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ── Error handler global ─────────────────────────────────────────────────
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.error(f"Error en update {update}: {context.error}", exc_info=context.error)

    app.add_error_handler(error_handler)

    # ── Warm-up de Ollama al arrancar ─────────────────────────────────────────
    async def warmup_ollama():
        logging.info("🔥 Calentando Ollama...")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    OLLAMA_URL,
                    json={"model": MODEL_NAME, "prompt": "init", "stream": False, "options": {"num_predict": 1}},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as r:
                    if r.status == 200:
                        logging.info("✅ Ollama warm-up completo — modelo en VRAM")
                    else:
                        logging.warning(f"⚠️  Ollama respondió {r.status} en warm-up")
        except Exception as e:
            logging.warning(f"⚠️  Ollama warm-up falló: {e} — el bot sigue pero la primera respuesta puede tardar")

    loop.run_until_complete(warmup_ollama())

    # Comandos
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("manga",   cmd_manga))
    app.add_handler(CommandHandler("arcade",  cmd_arcade))
    app.add_handler(CommandHandler("invite",  cmd_invite))
    app.add_handler(CommandHandler("top",     cmd_top))
    app.add_handler(CommandHandler("web",     cmd_web))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("misimg",  cmd_misimg))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("gta6",    cmd_gta6))
    app.add_handler(CommandHandler("vice",    cmd_vice))
    app.add_handler(CommandHandler("creditos", cmd_creditos))

    # Stars / Pagos
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pago_exitoso))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_trivia,  pattern=r"^trivia_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_comprar_pack,  pattern=r"^comprar_"))
    app.add_handler(CallbackQueryHandler(callback_general, pattern=r"^(nueva_trivia|ir_manga|invite|ver_premium|cancelar|ir_vice|ir_gta6|refresh_gta6)$"))

    logging.info(f"🤖 MangaVault Bot v3 — Miami Vice Criminal Edition — modelo: {MODEL_NAME}")
    logging.info(f"⭐ Packs Stars: {[p['id'] for p in PACKS_STARS]}")
    logging.info(f"🔑 Admin ID: {ADMIN_ID}")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot apagado.")
