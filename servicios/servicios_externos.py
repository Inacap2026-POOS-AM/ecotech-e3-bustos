"""Lógica de negocio: consulta la API, guarda en la base y, si la API falla,
usa el Plan B (último dato guardado, indicando su antigüedad)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import config
from seguridad.validaciones import MONEDAS, validar_ciudad, validar_moneda
from .api_cliente import ErrorApi
from .deserializadores import (CiudadNoEncontrada, DeserializadorClima,
                               DeserializadorIndicadores, ErrorDeserializacion)

log = logging.getLogger(__name__)

ORIGEN_API = "api"
ORIGEN_LOCAL = "local"
ORIGEN_SIN_DATOS = "sin_datos"


@dataclass
class Resultado:
    datos: Any
    origen: str
    aviso: Optional[str] = None


def antiguedad(obtenido_en):
    """'hace 2 h 15 min' a partir del campo obtenido_en."""
    try:
        fecha = datetime.fromisoformat(obtenido_en)
    except (TypeError, ValueError):
        return "antigüedad desconocida"
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    minutos = int((datetime.now(timezone.utc) - fecha).total_seconds() // 60)
    if minutos < 1:
        return "hace menos de 1 minuto"
    if minutos < 60:
        return "hace %d min" % minutos
    horas, minutos = divmod(minutos, 60)
    if horas < 48:
        return "hace %d h %d min" % (horas, minutos)
    return "hace %d días" % (horas // 24)


class ServicioClima:
    def __init__(self, cliente, almacen):
        self.cliente = cliente
        self.almacen = almacen
        self.deserializador = DeserializadorClima()

    def _desde_api(self, ciudad):
        geo = self.cliente.get_json(config.URL_GEOCODING, params={
            "name": ciudad, "count": 1, "language": "es", "format": "json",
        })
        ubicacion = self.deserializador.ubicacion(geo)
        respuesta = self.cliente.get_json(config.URL_CLIMA, params={
            "latitude": ubicacion["latitud"],
            "longitude": ubicacion["longitud"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        })
        return self.deserializador.clima(ubicacion, respuesta)

    def consultar(self, ciudad):
        """Devuelve (Resultado, estado_guardado). Puede lanzar ErrorValidacion si la ciudad es inválida."""
        ciudad = validar_ciudad(ciudad)
        try:
            clima = self._desde_api(ciudad)
            estado = self.almacen.guardar_clima(clima)
            return Resultado(clima, ORIGEN_API), estado
        except CiudadNoEncontrada as error:
            return Resultado(None, ORIGEN_SIN_DATOS, error.mensaje_usuario), None
        except (ErrorApi, ErrorDeserializacion) as error:
            log.warning("Clima de '%s' no disponible desde la API: %s", ciudad, error)
            guardado = self.almacen.ultimo_clima(ciudad)
            if guardado:
                return Resultado(guardado, ORIGEN_LOCAL, error.mensaje_usuario), None
            return Resultado(None, ORIGEN_SIN_DATOS, error.mensaje_usuario), None


class ServicioIndicadores:
    def __init__(self, cliente, almacen):
        self.cliente = cliente
        self.almacen = almacen
        self.deserializador = DeserializadorIndicadores()

    def actualizar(self):
        """Trae dólar, euro, UF y UTM. Devuelve (Resultado con dict codigo->Indicador, conteo)."""
        conteo = {"nuevo": 0, "actualizado": 0}
        try:
            respuesta = self.cliente.get_json(config.URL_INDICADORES)
            indicadores = self.deserializador.todos(respuesta)
            for indicador in indicadores:
                conteo[self.almacen.guardar_indicador(indicador)] += 1
            return Resultado({i.codigo: i for i in indicadores}, ORIGEN_API), conteo
        except (ErrorApi, ErrorDeserializacion) as error:
            log.warning("Indicadores no disponibles desde la API: %s", error)
            guardados = {}
            for codigo in DeserializadorIndicadores.CODIGOS:
                indicador = self.almacen.ultimo_indicador(codigo)
                if indicador:
                    guardados[codigo] = indicador
            if guardados:
                return Resultado(guardados, ORIGEN_LOCAL, error.mensaje_usuario), conteo
            return Resultado(None, ORIGEN_SIN_DATOS, error.mensaje_usuario), conteo

    def convertir(self, monto_clp, moneda, indicadores):
        """Pesos chilenos -> moneda del país del proyecto. indicadores = dict de actualizar()."""
        moneda = validar_moneda(moneda)
        codigo = MONEDAS[moneda]
        if codigo is None:
            return float(monto_clp), None
        indicador = (indicadores or {}).get(codigo)
        if not indicador:
            return None, None
        return monto_clp / indicador.valor, indicador
