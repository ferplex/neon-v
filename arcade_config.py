"""
arcade_config.py — Configuración compartida entre mangavault.py y credits_api.py
Ambos archivos deben vivir en la misma carpeta en kawai.
"""
import os

# Puntos de arcade necesarios para desbloquear +1 imagen bonus
ARCADE_PTS_POR_IMAGEN = int(os.getenv("ARCADE_PTS_POR_IMAGEN", "200"))

# Tope de puntos de arcade que se aceptan por día por usuario (anti-farm)
ARCADE_PTS_MAX_DIA = int(os.getenv("ARCADE_PTS_MAX_DIA", "600"))

# Tope de puntos aceptados en una sola partida/envío (anti-farm / anti-cheat básico)
ARCADE_PTS_MAX_ENVIO = int(os.getenv("ARCADE_PTS_MAX_ENVIO", "2000"))

# Secreto compartido entre la página (JS) y la API — cámbialo por el tuyo
# Exporta ARCADE_SYNC_SECRET en kawai antes de correr credits_api.py,
# y pon el MISMO valor en el <script> de index_1_.html (constante ARCADE_SECRET)
ARCADE_SYNC_SECRET = os.getenv("ARCADE_SYNC_SECRET", "nautilus-cambia-esto")

# Ruta a la base de datos compartida (misma que usa mangavault.py)
DB_FILE = os.getenv("MANGAVAULT_DB", "mangavault.db")

# Orígenes permitidos para el API (tus páginas públicas)
ORIGENES_PERMITIDOS = [
    "https://ferplex.github.io",
    "https://nautiluslaarhc.blogspot.com",
]
