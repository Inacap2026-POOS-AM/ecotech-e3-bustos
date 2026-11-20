"""Tablas para Supabase (PostgreSQL) y para la copia local (SQLite).

Los UNIQUE son los que garantizan la idempotencia: aunque el script corra dos
veces, el mismo dato (misma ciudad + misma hora, o mismo indicador + misma fecha)
no puede quedar dos veces. Las fechas se guardan como texto ISO en ambas bases.

Las sentencias están escritas completas (sin armar SQL con texto) aunque se
repitan un poco entre SQLite y PostgreSQL.
"""

import logging

from .base_datos import ErrorBaseDatos

log = logging.getLogger(__name__)

TABLAS_SUPABASE = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        nombre_usuario  TEXT NOT NULL UNIQUE,
        hash_password   TEXT NOT NULL,
        rol             TEXT NOT NULL DEFAULT 'usuario',
        creado_en       TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS proyectos (
        id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        nombre  TEXT NOT NULL UNIQUE,
        ciudad  TEXT NOT NULL,
        pais    TEXT NOT NULL,
        moneda  TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS empleados (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        rut         TEXT    NOT NULL UNIQUE,
        nombre      TEXT    NOT NULL,
        sueldo_clp  INTEGER NOT NULL CHECK (sueldo_clp > 0),
        proyecto    TEXT    NOT NULL REFERENCES proyectos(nombre))""",
    """CREATE TABLE IF NOT EXISTS clima (
        id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        ciudad             TEXT             NOT NULL,
        clave_busqueda     TEXT             NOT NULL,
        pais               TEXT             NOT NULL,
        latitud            DOUBLE PRECISION NOT NULL,
        longitud           DOUBLE PRECISION NOT NULL,
        temperatura        DOUBLE PRECISION NOT NULL,
        humedad            INTEGER          NOT NULL,
        codigo_tiempo      INTEGER          NOT NULL,
        descripcion        TEXT             NOT NULL,
        viento             DOUBLE PRECISION NOT NULL,
        fecha_observacion  TEXT             NOT NULL,
        obtenido_en        TEXT             NOT NULL,
        UNIQUE (clave_busqueda, pais, fecha_observacion))""",
    """CREATE TABLE IF NOT EXISTS indicadores (
        id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        codigo       TEXT             NOT NULL,
        nombre       TEXT             NOT NULL,
        unidad       TEXT             NOT NULL,
        valor        DOUBLE PRECISION NOT NULL,
        fecha        TEXT             NOT NULL,
        obtenido_en  TEXT             NOT NULL,
        UNIQUE (codigo, fecha))""",
    # Supabase publica las tablas de "public" en su API REST. Con RLS activado y sin
    # políticas, nadie puede leerlas por esa vía (por ejemplo los hashes de usuarios).
    # Este script entra directo a PostgreSQL como dueño de las tablas, así que sí puede.
    "ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE proyectos ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE empleados ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE clima ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE indicadores ENABLE ROW LEVEL SECURITY",
]

TABLAS_LOCAL = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_usuario  TEXT NOT NULL UNIQUE,
        hash_password   TEXT NOT NULL,
        rol             TEXT NOT NULL DEFAULT 'usuario',
        creado_en       TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS proyectos (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre  TEXT NOT NULL UNIQUE,
        ciudad  TEXT NOT NULL,
        pais    TEXT NOT NULL,
        moneda  TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS empleados (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        rut         TEXT    NOT NULL UNIQUE,
        nombre      TEXT    NOT NULL,
        sueldo_clp  INTEGER NOT NULL CHECK (sueldo_clp > 0),
        proyecto    TEXT    NOT NULL REFERENCES proyectos(nombre))""",
    """CREATE TABLE IF NOT EXISTS clima (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        ciudad             TEXT    NOT NULL,
        clave_busqueda     TEXT    NOT NULL,
        pais               TEXT    NOT NULL,
        latitud            REAL    NOT NULL,
        longitud           REAL    NOT NULL,
        temperatura        REAL    NOT NULL,
        humedad            INTEGER NOT NULL,
        codigo_tiempo      INTEGER NOT NULL,
        descripcion        TEXT    NOT NULL,
        viento             REAL    NOT NULL,
        fecha_observacion  TEXT    NOT NULL,
        obtenido_en        TEXT    NOT NULL,
        UNIQUE (clave_busqueda, pais, fecha_observacion))""",
    """CREATE TABLE IF NOT EXISTS indicadores (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo       TEXT NOT NULL,
        nombre       TEXT NOT NULL,
        unidad       TEXT NOT NULL,
        valor        REAL NOT NULL,
        fecha        TEXT NOT NULL,
        obtenido_en  TEXT NOT NULL,
        UNIQUE (codigo, fecha))""",
]

# Datos de ejemplo de EcoTech (proyectos y empleados de la E2)
PROYECTOS = [
    ("Parque Solar Atacama", "Antofagasta", "Chile", "CLP"),
    ("Eólica Castilla", "Madrid", "España", "EUR"),
    ("Smart Grid Florida", "Miami", "Estados Unidos", "USD"),
]

EMPLEADOS = [
    ("12345678-5", "Camila Rojas", 1_450_000, "Parque Solar Atacama"),
    ("15987654-3", "Diego Muñoz", 1_200_000, "Parque Solar Atacama"),
    ("17654321-K", "Valentina Soto", 1_800_000, "Eólica Castilla"),
    ("19111222-4", "Matías Herrera", 2_100_000, "Smart Grid Florida"),
    ("16222333-1", "Fernanda Vega", 1_650_000, "Smart Grid Florida"),
]

SQL_PROYECTO = ("INSERT INTO proyectos (nombre, ciudad, pais, moneda) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (nombre) DO NOTHING")
SQL_EMPLEADO = ("INSERT INTO empleados (rut, nombre, sueldo_clp, proyecto) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (rut) DO NOTHING")


def inicializar(bd):
    tablas = TABLAS_SUPABASE if bd.nombre == "Supabase" else TABLAS_LOCAL
    bd.ejecutar_varias([(sql, ()) for sql in tablas])
    datos = [(SQL_PROYECTO, p) for p in PROYECTOS] + [(SQL_EMPLEADO, e) for e in EMPLEADOS]
    try:
        bd.ejecutar_varias(datos)
    except ErrorBaseDatos:
        log.warning("No se pudieron cargar los datos de ejemplo en %s", bd.nombre)
