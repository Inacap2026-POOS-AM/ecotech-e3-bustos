"""Cliente HTTP con timeout, reintentos acotados y backoff exponencial.

Reglas:
- Todas las peticiones llevan timeout explícito.
- 4xx (menos 429) NO se reintentan: el error es de la petición, repetirla da lo mismo.
- 429 se reintenta respetando el header Retry-After (con un tope).
- 5xx, timeouts y errores de red SÍ se reintentan, con espera 1s, 2s, 4s...
- verify=True siempre (el valor por defecto de requests), nunca se desactiva SSL.
"""

import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)


class ErrorApi(Exception):
    """Error base. mensaje_usuario es lo único que se le muestra a la persona."""

    def __init__(self, mensaje_usuario, codigo=None):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario
        self.codigo = codigo


class ErrorCliente(ErrorApi):
    """4xx: la petición está mal (URL inválida, recurso que no existe, etc.)."""


class ErrorServidor(ErrorApi):
    """5xx o 429 que siguieron fallando después de todos los reintentos."""


class ErrorRed(ErrorApi):
    """Sin conexión, DNS que no resuelve o timeout."""


class ErrorRespuesta(ErrorApi):
    """La API respondió 200 pero el cuerpo no es JSON válido."""


def _url_segura(url):
    """Para los logs: solo host y ruta, sin parámetros (ahí podría ir una API key)."""
    partes = urlsplit(url)
    return partes.netloc + partes.path


class ApiCliente:
    def __init__(self, timeout, max_intentos=3, backoff_base=1.0, espera_maxima=30,
                 sesion=None, dormir=time.sleep):
        if not timeout:
            raise ValueError("El cliente necesita un timeout explícito")
        self.timeout = timeout
        self.max_intentos = max(1, min(int(max_intentos), 4))
        self.backoff_base = backoff_base
        self.espera_maxima = espera_maxima
        self.sesion = sesion or requests.Session()
        self.sesion.headers.update({"User-Agent": "EcoTech-Solutions/1.0 (proyecto academico)"})
        # se inyecta para poder probar sin esperar de verdad
        self._dormir = dormir

    def _espera_backoff(self, intento):
        # 1, 2, 4 segundos (+ un poco de azar para no pegarle todos a la vez)
        espera = self.backoff_base * (2 ** (intento - 1)) + random.uniform(0, 0.3)
        return min(espera, self.espera_maxima)

    def _espera_retry_after(self, valor, intento):
        """Retry-After puede venir en segundos ("5") o como fecha HTTP."""
        if valor:
            try:
                segundos = float(valor)
            except ValueError:
                try:
                    fecha = parsedate_to_datetime(valor)
                    segundos = (fecha - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError):
                    segundos = None
            if segundos is not None:
                return max(0.0, min(segundos, self.espera_maxima))
        return self._espera_backoff(intento)

    def get_json(self, url, params=None):
        destino = _url_segura(url)
        for intento in range(1, self.max_intentos + 1):
            ultimo = intento == self.max_intentos
            try:
                respuesta = self.sesion.get(url, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as error:
                log.warning("Intento %s/%s a %s falló por red: %s",
                            intento, self.max_intentos, destino, type(error).__name__)
                if ultimo:
                    raise ErrorRed("No hay conexión con el servicio externo.") from error
                self._dormir(self._espera_backoff(intento))
                continue
            except requests.RequestException as error:
                # URL mal escrita (sin http, caracteres raros...). Reintentar no sirve.
                log.error("Petición inválida a %s: %s", destino, type(error).__name__)
                raise ErrorCliente("La dirección del servicio no es válida.") from error

            codigo = respuesta.status_code

            if 200 <= codigo < 300:
                try:
                    return respuesta.json()
                except ValueError as error:
                    log.error("Respuesta no JSON desde %s", destino)
                    raise ErrorRespuesta("El servicio respondió en un formato inesperado.") from error

            if codigo == 429:
                espera = self._espera_retry_after(respuesta.headers.get("Retry-After"), intento)
                log.warning("429 en %s, intento %s/%s, esperando %.1fs",
                            destino, intento, self.max_intentos, espera)
                if ultimo:
                    raise ErrorServidor("El servicio está recibiendo demasiadas consultas.", codigo)
                self._dormir(espera)
                continue

            if 500 <= codigo < 600:
                log.warning("Error %s en %s, intento %s/%s", codigo, destino, intento, self.max_intentos)
                if ultimo:
                    raise ErrorServidor("El servicio externo no está disponible.", codigo)
                self._dormir(self._espera_backoff(intento))
                continue

            # 4xx y cualquier otro código raro: no se reintenta
            log.error("Error %s en %s (no se reintenta)", codigo, destino)
            if codigo == 404:
                raise ErrorCliente("El recurso consultado no existe (404).", codigo)
            if codigo in (401, 403):
                raise ErrorCliente("Acceso denegado por el servicio externo.", codigo)
            raise ErrorCliente("El servicio rechazó la consulta (código %s)." % codigo, codigo)

        # no debería llegar aquí, pero por si acaso
        raise ErrorServidor("El servicio externo no está disponible.")
