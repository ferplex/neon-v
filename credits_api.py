"""
credits_api.py — API de sincronización NEON VAULT ↔ MangaVault Bot
╔═══════════════════════════════════════════════════════╗
║  Recibe los puntos del arcade y los convierte en       ║
║  créditos (imágenes bonus) en la misma DB del bot.     ║
╚═══════════════════════════════════════════════════════╝

Corre APARTE del bot (proceso independiente), pero comparte
la misma mangavault.db. Así no tocamos el event loop de
python-telegram-bot para nada.

Uso en kawai:
    export ARCADE_SYNC_SECRET="pon-algo-largo-aqui"
    python3 credits_api.py
    # -> escucha en http://0.0.0.0:8092

Luego expón el puerto 8092 por Caddy con HTTPS (igual que hiciste
con Ollama/TTS) porque GitHub Pages y Blogger son HTTPS y bloquean
contenido mixto (http). Algo tipo:

    creditos.tudominio.com {
        reverse_proxy localhost:8092
    }

Endpoints:
    POST /api/arcade/score    body: {"uid": 123, "game": "space", "score": 340, "secret": "..."}
    GET  /api/arcade/balance?uid=123
"""
import logging
import sqlite3
import time
from aiohttp import web

from arcade_config import (
    ARCADE_PTS_POR_IMAGEN, ARCADE_PTS_MAX_DIA, ARCADE_PTS_MAX_ENVIO,
    ARCADE_SYNC_SECRET, DB_FILE, ORIGENES_PERMITIDOS,
)

logging.basicConfig(format="%(asctime)s - credits_api - %(levelname)s - %(message)s", level=logging.INFO)

JUEGOS_VALIDOS = {"ark", "snake", "tet", "space", "mario", "sf"}  # deja espacio a los juegos nuevos

# anti-spam en memoria: (uid, game) -> timestamp del último envío aceptado
_ultimo_envio = {}
COOLDOWN_SEG = 8  # no aceptar 2 envíos del mismo juego antes de esto


def db_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def asegurar_columnas():
    """Agrega las columnas de arcade a 'usuarios' si no existen (no rompe la DB del bot)."""
    con = db_con()
    cols = {r["name"] for r in con.execute("PRAGMA table_info(usuarios)")}
    if "arcade_pts" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN arcade_pts INTEGER DEFAULT 0")
    if "arcade_pts_hoy" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN arcade_pts_hoy INTEGER DEFAULT 0")
    if "arcade_reset" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN arcade_reset REAL DEFAULT 0")
    if "arcade_bonus_otorgado" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN arcade_bonus_otorgado INTEGER DEFAULT 0")
    con.commit()
    con.close()


def get_or_create_usuario(con, uid: int):
    row = con.execute("SELECT * FROM usuarios WHERE user_id=?", (uid,)).fetchone()
    if not row:
        # Si el usuario nunca usó /start, lo creamos igual para no perder sus puntos
        con.execute("INSERT INTO usuarios (user_id) VALUES (?)", (uid,))
        con.commit()
        row = con.execute("SELECT * FROM usuarios WHERE user_id=?", (uid,)).fetchone()
    return row


def cors_headers(request: web.Request) -> dict:
    origin = request.headers.get("Origin", "")
    allow = origin if origin in ORIGENES_PERMITIDOS else ORIGENES_PERMITIDOS[0]
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


async def options_handler(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=cors_headers(request))


async def enviar_score(request: web.Request) -> web.Response:
    headers = cors_headers(request)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "json inválido"}, status=400, headers=headers)

    if data.get("secret") != ARCADE_SYNC_SECRET:
        return web.json_response({"ok": False, "error": "secreto inválido"}, status=401, headers=headers)

    try:
        uid = int(data.get("uid"))
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "uid/score inválidos"}, status=400, headers=headers)

    game = str(data.get("game", ""))[:20]
    if game not in JUEGOS_VALIDOS:
        return web.json_response({"ok": False, "error": "juego desconocido"}, status=400, headers=headers)

    score = max(0, min(score, ARCADE_PTS_MAX_ENVIO))  # anti-cheat básico

    now = time.time()
    key = (uid, game)
    if key in _ultimo_envio and now - _ultimo_envio[key] < COOLDOWN_SEG:
        return web.json_response({"ok": False, "error": "muy rápido, espera un poco"}, status=429, headers=headers)
    _ultimo_envio[key] = now

    con = db_con()
    row = get_or_create_usuario(con, uid)

    # reset diario del contador de puntos de arcade
    pts_hoy = row["arcade_pts_hoy"] or 0
    reset_ts = row["arcade_reset"] or 0
    if now - reset_ts > 86400:
        pts_hoy = 0
        reset_ts = now

    espacio_hoy = max(0, ARCADE_PTS_MAX_DIA - pts_hoy)
    pts_aceptados = min(score, espacio_hoy)

    nuevo_total = (row["arcade_pts"] or 0) + pts_aceptados
    nuevo_pts_hoy = pts_hoy + pts_aceptados

    # convertir puntos acumulados en imágenes bonus (sin perder el resto)
    ya_otorgado = row["arcade_bonus_otorgado"] or 0
    bonus_ganable = nuevo_total // ARCADE_PTS_POR_IMAGEN
    nuevas_imagenes = max(0, bonus_ganable - ya_otorgado)

    con.execute(
        """UPDATE usuarios SET
             arcade_pts=?, arcade_pts_hoy=?, arcade_reset=?,
             arcade_bonus_otorgado=?, bonus_imagenes=bonus_imagenes+?
           WHERE user_id=?""",
        (nuevo_total, nuevo_pts_hoy, reset_ts, ya_otorgado + nuevas_imagenes, nuevas_imagenes, uid),
    )
    con.commit()
    con.close()

    faltan = ARCADE_PTS_POR_IMAGEN - (nuevo_total % ARCADE_PTS_POR_IMAGEN)
    logging.info(f"uid={uid} game={game} +{pts_aceptados}pts (de {score}) total={nuevo_total} nuevas_img={nuevas_imagenes}")

    return web.json_response({
        "ok": True,
        "pts_aceptados": pts_aceptados,
        "arcade_pts_total": nuevo_total,
        "imagenes_ganadas_ahora": nuevas_imagenes,
        "pts_para_siguiente_imagen": faltan,
    }, headers=headers)


async def ver_balance(request: web.Request) -> web.Response:
    headers = cors_headers(request)
    try:
        uid = int(request.query.get("uid", ""))
    except ValueError:
        return web.json_response({"ok": False, "error": "uid inválido"}, status=400, headers=headers)

    con = db_con()
    row = con.execute(
        "SELECT arcade_pts, arcade_bonus_otorgado FROM usuarios WHERE user_id=?", (uid,)
    ).fetchone()
    con.close()

    if not row:
        return web.json_response({"ok": True, "arcade_pts_total": 0, "imagenes_bonus": 0}, headers=headers)

    return web.json_response({
        "ok": True,
        "arcade_pts_total": row["arcade_pts"] or 0,
        "imagenes_bonus": row["arcade_bonus_otorgado"] or 0,
    }, headers=headers)


def main():
    asegurar_columnas()
    app = web.Application()
    app.router.add_post("/api/arcade/score", enviar_score)
    app.router.add_get("/api/arcade/balance", ver_balance)
    app.router.add_route("OPTIONS", "/api/arcade/score", options_handler)
    app.router.add_route("OPTIONS", "/api/arcade/balance", options_handler)
    logging.info("🕹️  Credits API arriba en http://0.0.0.0:8092")
    web.run_app(app, host="0.0.0.0", port=8092)


if __name__ == "__main__":
    main()
