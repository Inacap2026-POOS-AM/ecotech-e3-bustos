"""Consultas SQL por tabla. Cada repositorio trabaja sobre UNA base (Supabase o local).
TODAS las consultas son parametrizadas con ?: nunca se arma SQL con f-strings,
% ni concatenando texto del usuario."""

from datetime import datetime, timezone

from dominio import Clima, Empleado, Indicador, Proyecto
from seguridad.validaciones import normalizar


class RepositorioUsuarios:
    def __init__(self, bd):
        self.bd = bd

    def buscar(self, nombre_usuario):
        return self.bd.fila(
            "SELECT id, nombre_usuario, hash_password, rol, creado_en FROM usuarios WHERE nombre_usuario = ?",
            (nombre_usuario,),
        )

    def crear(self, nombre_usuario, hash_password, rol, creado_en=None):
        """ON CONFLICT DO NOTHING: si ya existe (por ejemplo al copiar entre bases) no se duplica."""
        creado_en = creado_en or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        fila = self.bd.fila(
            "INSERT INTO usuarios (nombre_usuario, hash_password, rol, creado_en) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (nombre_usuario) DO NOTHING RETURNING id",
            (nombre_usuario, hash_password, rol, creado_en),
        )
        return fila["id"] if fila else None

    def todos(self):
        return self.bd.filas(
            "SELECT nombre_usuario, hash_password, rol, creado_en FROM usuarios ORDER BY id")

    def contar(self):
        return self.bd.fila("SELECT COUNT(*) AS total FROM usuarios")["total"]


class RepositorioClima:
    def __init__(self, bd):
        self.bd = bd

    def guardar(self, clima):
        """Inserta o actualiza. Devuelve 'nuevo' o 'actualizado' (para ver la idempotencia)."""
        clave = normalizar(clima.ciudad)
        existe = self.bd.fila(
            "SELECT id FROM clima WHERE clave_busqueda = ? AND pais = ? AND fecha_observacion = ?",
            (clave, clima.pais, clima.fecha_observacion),
        )
        self.bd.ejecutar(
            """INSERT INTO clima (ciudad, clave_busqueda, pais, latitud, longitud, temperatura,
                                  humedad, codigo_tiempo, descripcion, viento,
                                  fecha_observacion, obtenido_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (clave_busqueda, pais, fecha_observacion) DO UPDATE SET
                   temperatura = excluded.temperatura,
                   humedad = excluded.humedad,
                   codigo_tiempo = excluded.codigo_tiempo,
                   descripcion = excluded.descripcion,
                   viento = excluded.viento,
                   obtenido_en = excluded.obtenido_en""",
            (clima.ciudad, clave, clima.pais, clima.latitud, clima.longitud, clima.temperatura,
             clima.humedad, clima.codigo_tiempo, clima.descripcion, clima.viento,
             clima.fecha_observacion, clima.obtenido_en),
        )
        return "actualizado" if existe else "nuevo"

    def ultimo(self, ciudad):
        """Plan B: el registro más reciente guardado de esa ciudad."""
        clave = normalizar(ciudad)
        fila = self.bd.fila(
            """SELECT * FROM clima
               WHERE clave_busqueda = ? OR clave_busqueda LIKE ?
               ORDER BY obtenido_en DESC LIMIT 1""",
            (clave, clave + "%"),
        )
        if not fila:
            return None
        return Clima(fila["ciudad"], fila["pais"], fila["latitud"], fila["longitud"],
                     fila["temperatura"], fila["humedad"], fila["codigo_tiempo"],
                     fila["descripcion"], fila["viento"], fila["fecha_observacion"],
                     fila["obtenido_en"])

    def contar(self):
        return self.bd.fila("SELECT COUNT(*) AS total FROM clima")["total"]


class RepositorioIndicadores:
    def __init__(self, bd):
        self.bd = bd

    def guardar(self, indicador):
        existe = self.bd.fila(
            "SELECT id FROM indicadores WHERE codigo = ? AND fecha = ?",
            (indicador.codigo, indicador.fecha),
        )
        self.bd.ejecutar(
            """INSERT INTO indicadores (codigo, nombre, unidad, valor, fecha, obtenido_en)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (codigo, fecha) DO UPDATE SET
                   valor = excluded.valor,
                   obtenido_en = excluded.obtenido_en""",
            (indicador.codigo, indicador.nombre, indicador.unidad, indicador.valor,
             indicador.fecha, indicador.obtenido_en),
        )
        return "actualizado" if existe else "nuevo"

    def ultimo(self, codigo):
        fila = self.bd.fila(
            "SELECT * FROM indicadores WHERE codigo = ? ORDER BY fecha DESC, obtenido_en DESC LIMIT 1",
            (codigo,),
        )
        if not fila:
            return None
        return Indicador(fila["codigo"], fila["nombre"], fila["unidad"], fila["valor"],
                         fila["fecha"], fila["obtenido_en"])

    def contar(self):
        return self.bd.fila("SELECT COUNT(*) AS total FROM indicadores")["total"]


class RepositorioProyectos:
    def __init__(self, bd):
        self.bd = bd

    def listar(self):
        proyectos = []
        for fila in self.bd.filas("SELECT id, nombre, ciudad, pais, moneda FROM proyectos ORDER BY id"):
            proyecto = Proyecto(fila["nombre"], fila["ciudad"], fila["pais"], fila["moneda"], fila["id"])
            for emp in self.bd.filas(
                "SELECT id, rut, nombre, sueldo_clp FROM empleados WHERE proyecto = ? ORDER BY nombre",
                (fila["nombre"],),
            ):
                proyecto.empleados.append(Empleado(emp["rut"], emp["nombre"], emp["sueldo_clp"], id=emp["id"]))
            proyectos.append(proyecto)
        return proyectos
