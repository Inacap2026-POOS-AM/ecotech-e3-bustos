"""Configuración del sistema. Todo lo sensible o configurable sale del .env
(que NO se sube al repo). Si falta una variable se usa un valor por defecto seguro."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _leer_float(nombre, defecto, minimo, maximo):
    try:
        valor = float(os.getenv(nombre, defecto))
    except ValueError:
        valor = defecto
    return max(minimo, min(valor, maximo))


def _leer_int(nombre, defecto, minimo, maximo):
    try:
        valor = int(os.getenv(nombre, defecto))
    except ValueError:
        valor = defecto
    return max(minimo, min(valor, maximo))


# --- APIs externas (las dos son públicas y no piden API key) ---
URL_GEOCODING = os.getenv("URL_GEOCODING", "https://geocoding-api.open-meteo.com/v1/search")
URL_CLIMA = os.getenv("URL_CLIMA", "https://api.open-meteo.com/v1/forecast")
URL_INDICADORES = os.getenv("URL_INDICADORES", "https://mindicador.cl/api")

# Si algún día se cambia a una API con llave, se lee de aquí y nunca se escribe en el código
API_KEY_CLIMA = os.getenv("API_KEY_CLIMA", "")

# --- Resiliencia ---
# timeout en segundos (conexión, lectura). Nunca se deja sin timeout.
HTTP_TIMEOUT = (
    _leer_float("HTTP_TIMEOUT_CONEXION", 3.05, 1, 15),
    _leer_float("HTTP_TIMEOUT_LECTURA", 10, 1, 30),
)
# máximo de intentos acotado entre 1 y 4 aunque alguien ponga 100 en el .env
HTTP_MAX_INTENTOS = _leer_int("HTTP_MAX_INTENTOS", 3, 1, 4)
HTTP_BACKOFF_BASE = _leer_float("HTTP_BACKOFF_BASE", 1.0, 0.1, 5)
# tope para Retry-After, para que la app no quede pegada esperando
HTTP_ESPERA_MAXIMA = _leer_float("HTTP_ESPERA_MAXIMA", 30, 1, 120)

# --- Base de datos ---
# Principal: Supabase (PostgreSQL). La URL trae la contraseña, por eso solo vive en el .env
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "").strip()
# Certificado de la CA de Supabase para verificar el SSL (no es secreto, se puede subir al repo)
SUPABASE_CA_CERT = BASE_DIR / os.getenv("SUPABASE_CA_CERT", "certs/prod-ca-2021.crt")
# Copia local para el Plan B (cuando no hay internet tampoco hay Supabase)
DB_PATH = BASE_DIR / os.getenv("DB_LOCAL", "ecotech_local.db")

# --- Logs ---
LOG_PATH = BASE_DIR / "logs" / "ecotech.log"


def configurar_logs():
    """Los detalles técnicos van al archivo de log, al usuario solo le llega un mensaje genérico."""
    LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
