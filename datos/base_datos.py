"""Conexiones a la base de datos.

- Principal: Supabase (PostgreSQL en la nube), con pg8000 y SSL verificado.
- Copia local: SQLite, para el Plan B cuando no hay internet (Supabase tampoco
  responde si se corta el WiFi).

BaseDatos envuelve las dos conexiones para que los repositorios usen la misma
forma de consultar. Las consultas se escriben siempre con marcadores ? y los
valores van aparte (consultas parametrizadas). En PostgreSQL el marcador es %s,
por eso _sql() solo cambia el símbolo del marcador; el texto del usuario nunca
se mete dentro del SQL.
"""

import logging
import socket
import sqlite3
import ssl
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pg8000.dbapi

log = logging.getLogger(__name__)

ERRORES_BD = (sqlite3.Error, pg8000.dbapi.Error, OSError, socket.timeout)


class ErrorBaseDatos(Exception):
    def __init__(self, mensaje_usuario):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario


class BaseDatos:
    def __init__(self, conexion, nombre, marcador="?"):
        self.con = conexion
        self.nombre = nombre
        self.marcador = marcador

    def _sql(self, sql):
        return sql if self.marcador == "?" else sql.replace("?", self.marcador)

    def _correr(self, sql, parametros):
        cursor = self.con.cursor()
        cursor.execute(self._sql(sql), tuple(parametros))
        if cursor.description is None:
            return []
        columnas = [c[0] for c in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    def filas(self, sql, parametros=()):
        try:
            resultado = self._correr(sql, parametros)
            self.con.commit()
            return resultado
        except ERRORES_BD as error:
            self._deshacer()
            log.warning("Error en base %s: %s", self.nombre, type(error).__name__)
            raise ErrorBaseDatos("No se pudo consultar la base de datos %s." % self.nombre) from error

    def fila(self, sql, parametros=()):
        resultado = self.filas(sql, parametros)
        return resultado[0] if resultado else None

    def ejecutar(self, sql, parametros=()):
        return self.filas(sql, parametros)

    def ejecutar_varias(self, sentencias):
        """Varias sentencias en una sola transacción (si una falla, no queda nada a medias)."""
        try:
            for sql, parametros in sentencias:
                self._correr(sql, parametros)
            self.con.commit()
        except ERRORES_BD as error:
            self._deshacer()
            log.warning("Error en base %s: %s", self.nombre, type(error).__name__)
            raise ErrorBaseDatos("No se pudo escribir en la base de datos %s." % self.nombre) from error

    def _deshacer(self):
        try:
            self.con.rollback()
        except ERRORES_BD as error:
            # la conexión ya está caída, no hay nada que deshacer; se deja registro igual
            log.info("No se pudo hacer rollback en %s: %s", self.nombre, type(error).__name__)

    def cerrar(self):
        try:
            self.con.close()
        except ERRORES_BD as error:
            log.info("Conexión %s ya estaba cerrada: %s", self.nombre, type(error).__name__)


def conectar_local(ruta):
    conexion = sqlite3.connect(ruta, timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    return BaseDatos(conexion, "local", "?")


def _contexto_ssl(host, ruta_certificado):
    """SSL siempre verificado. Supabase firma con su propia CA, por eso se usa su certificado."""
    if host in ("localhost", "127.0.0.1"):
        return None  # solo para pruebas en el mismo PC
    ruta = Path(ruta_certificado) if ruta_certificado else None
    if ruta and ruta.is_file():
        return ssl.create_default_context(cafile=str(ruta))
    log.warning("No se encontró el certificado de Supabase; se usan los certificados del sistema")
    return ssl.create_default_context()


def conectar_supabase(url, ruta_certificado=None, timeout=5):
    """Devuelve BaseDatos o None si no se pudo conectar (sin internet, datos malos, etc.)."""
    if not url:
        log.info("SUPABASE_DB_URL vacío: se trabaja solo con la base local")
        return None
    partes = urlsplit(url)
    if partes.scheme not in ("postgres", "postgresql") or not partes.hostname:
        log.error("SUPABASE_DB_URL no tiene formato postgresql://...")
        return None
    try:
        conexion = pg8000.dbapi.connect(
            user=unquote(partes.username or ""),
            password=unquote(partes.password or ""),
            host=partes.hostname,
            port=partes.port or 5432,
            database=(partes.path or "/postgres").lstrip("/") or "postgres",
            ssl_context=_contexto_ssl(partes.hostname, ruta_certificado),
            timeout=timeout,
            application_name="ecotech-e3",
        )
    except ERRORES_BD as error:
        # nunca se escribe la URL en el log porque trae la contraseña
        log.warning("No se pudo conectar a Supabase (%s): %s", partes.hostname, type(error).__name__)
        return None
    log.info("Conectado a Supabase (%s)", partes.hostname)
    return BaseDatos(conexion, "Supabase", "%s")
