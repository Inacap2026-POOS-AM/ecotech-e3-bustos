"""Registro e inicio de sesión con bcrypt (hash + salt por usuario)."""

import logging

import bcrypt

from dominio import Usuario
from .validaciones import ErrorValidacion, validar_password_nueva, validar_usuario

log = logging.getLogger(__name__)

# hash de relleno: si el usuario no existe igual se hace un checkpw,
# así la respuesta tarda lo mismo y no se puede adivinar qué usuarios existen
_HASH_FALSO = bcrypt.hashpw(b"usuario-que-no-existe", bcrypt.gensalt(rounds=12))


class ServicioAutenticacion:
    def __init__(self, almacen, rondas=12):
        # almacen guarda en Supabase y en la copia local (ver datos/almacen.py)
        self.almacen = almacen
        self.rondas = rondas

    def registrar(self, nombre_usuario, password, rol="usuario"):
        nombre_usuario = validar_usuario(nombre_usuario)
        validar_password_nueva(password)
        if self.almacen.buscar_usuario(nombre_usuario):
            raise ErrorValidacion("Ese nombre de usuario ya está registrado.")
        # gensalt crea un salt aleatorio distinto cada vez; queda guardado dentro del hash
        hash_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=self.rondas))
        usuario_id = self.almacen.crear_usuario(nombre_usuario, hash_pw.decode("utf-8"), rol)
        log.info("Usuario registrado: %s", nombre_usuario)
        return Usuario(usuario_id, nombre_usuario, rol)

    def autenticar(self, nombre_usuario, password):
        """Devuelve el Usuario si las credenciales son correctas, si no None.
        El mensaje de error hacia afuera es siempre el mismo (no dice si falló el usuario o la clave)."""
        if not nombre_usuario or not nombre_usuario.strip() or not password:
            raise ErrorValidacion("Usuario y contraseña son obligatorios.")
        try:
            nombre_usuario = validar_usuario(nombre_usuario)
        except ErrorValidacion:
            bcrypt.checkpw(password.encode("utf-8")[:72], _HASH_FALSO)
            return None

        fila = self.almacen.buscar_usuario(nombre_usuario)
        hash_guardado = fila["hash_password"].encode("utf-8") if fila else _HASH_FALSO
        correcto = bcrypt.checkpw(password.encode("utf-8")[:72], hash_guardado)
        if fila and correcto:
            log.info("Inicio de sesión correcto: %s", nombre_usuario)
            return Usuario(fila["id"], fila["nombre_usuario"], fila["rol"])
        log.warning("Inicio de sesión fallido para: %s", nombre_usuario)
        return None
