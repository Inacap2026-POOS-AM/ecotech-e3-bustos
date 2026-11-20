"""Almacén: decide dónde se lee y se escribe.

- Escritura: en Supabase (si hay conexión) y SIEMPRE también en la copia local SQLite.
- Lectura: primero Supabase; si no responde, la copia local.
- Si Supabase falla en medio de la sesión (se cortó el WiFi), se marca como caído
  y el programa sigue con la copia local sin caerse. Se puede volver a conectar
  con reconectar() (lo hace la opción de sincronizar).
"""

import logging

from .base_datos import ErrorBaseDatos, conectar_supabase
from .esquema import inicializar
from .repositorios import (RepositorioClima, RepositorioIndicadores,
                           RepositorioProyectos, RepositorioUsuarios)

log = logging.getLogger(__name__)


class Almacen:
    def __init__(self, local, url_supabase=None, certificado=None, conectar=conectar_supabase):
        self.local = local
        self._url = url_supabase
        self._certificado = certificado
        self._conectar = conectar
        self.remota = None
        inicializar(self.local)
        self.reconectar()

    # ---------- estado de la conexión ----------

    @property
    def en_linea(self):
        return self.remota is not None

    def reconectar(self):
        if self.remota is not None or not self._url:
            return self.en_linea
        remota = self._conectar(self._url, self._certificado)
        if remota is None:
            return False
        try:
            inicializar(remota)
            self.remota = remota
            self.sincronizar_usuarios()
        except ErrorBaseDatos:
            log.warning("Supabase respondió pero no se pudieron crear las tablas")
            remota.cerrar()
            self.remota = None
        return self.en_linea

    def _marcar_caida(self):
        log.warning("Se perdió la conexión con Supabase; se sigue con la copia local")
        if self.remota:
            self.remota.cerrar()
        self.remota = None

    def _en_remota(self, operacion):
        """Corre operacion(bd) en Supabase. Si falla devuelve (False, None) en vez de caerse."""
        if not self.remota:
            return False, None
        try:
            return True, operacion(self.remota)
        except ErrorBaseDatos:
            self._marcar_caida()
            return False, None

    def _escribir(self, operacion):
        ok, resultado_remoto = self._en_remota(operacion)
        resultado_local = operacion(self.local)
        return resultado_remoto if ok else resultado_local

    def _leer(self, operacion):
        ok, resultado = self._en_remota(operacion)
        if ok and resultado:
            return resultado
        return operacion(self.local)

    # ---------- usuarios ----------

    def buscar_usuario(self, nombre):
        return self._leer(lambda bd: RepositorioUsuarios(bd).buscar(nombre))

    def crear_usuario(self, nombre, hash_password, rol):
        return self._escribir(lambda bd: RepositorioUsuarios(bd).crear(nombre, hash_password, rol))

    def sincronizar_usuarios(self):
        """Copia los usuarios (solo el hash) entre Supabase y la copia local,
        para poder iniciar sesión aunque no haya internet."""
        if not self.remota:
            return
        remotos = RepositorioUsuarios(self.remota).todos()
        locales = RepositorioUsuarios(self.local).todos()
        for u in remotos:
            RepositorioUsuarios(self.local).crear(u["nombre_usuario"], u["hash_password"], u["rol"], u["creado_en"])
        for u in locales:
            RepositorioUsuarios(self.remota).crear(u["nombre_usuario"], u["hash_password"], u["rol"], u["creado_en"])

    # ---------- clima e indicadores ----------

    def guardar_clima(self, clima):
        return self._escribir(lambda bd: RepositorioClima(bd).guardar(clima))

    def ultimo_clima(self, ciudad):
        return self._leer(lambda bd: RepositorioClima(bd).ultimo(ciudad))

    def guardar_indicador(self, indicador):
        return self._escribir(lambda bd: RepositorioIndicadores(bd).guardar(indicador))

    def ultimo_indicador(self, codigo):
        return self._leer(lambda bd: RepositorioIndicadores(bd).ultimo(codigo))

    def proyectos(self):
        return self._leer(lambda bd: RepositorioProyectos(bd).listar())

    def conteos(self):
        """Filas de clima e indicadores en la base principal (Supabase si está, si no la local)."""
        def contar(bd):
            return RepositorioClima(bd).contar(), RepositorioIndicadores(bd).contar()
        ok, resultado = self._en_remota(contar)
        return (resultado, "Supabase") if ok else (contar(self.local), "local")

    def cerrar(self):
        if self.remota:
            self.remota.cerrar()
        self.local.cerrar()
