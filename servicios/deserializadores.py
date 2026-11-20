"""Clases que validan el JSON de las APIs y lo convierten a objetos del dominio.
Nunca se confía en que la API mande lo que dice la documentación: se revisa
que cada campo exista, que sea del tipo correcto y que el valor tenga sentido."""

from datetime import datetime, timezone

from dominio import Clima, Indicador


class ErrorDeserializacion(Exception):
    def __init__(self, mensaje_usuario):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario


class CiudadNoEncontrada(ErrorDeserializacion):
    """La API de geocodificación no encontró la ciudad (no es error de red, no hay Plan B)."""


def ahora_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Deserializador:
    """Métodos comunes para leer campos de un diccionario con validación."""

    def _objeto(self, datos, nombre="respuesta"):
        if not isinstance(datos, dict):
            raise ErrorDeserializacion("Formato inválido en %s" % nombre)
        return datos

    def _texto(self, datos, clave, max_largo=120):
        valor = datos.get(clave)
        if not isinstance(valor, str) or not valor.strip():
            raise ErrorDeserializacion("Falta el campo '%s'" % clave)
        return valor.strip()[:max_largo]

    def _numero(self, datos, clave, minimo, maximo):
        valor = datos.get(clave)
        # bool es subclase de int en Python, por eso se descarta aparte
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErrorDeserializacion("El campo '%s' no es numérico" % clave)
        if not minimo <= valor <= maximo:
            raise ErrorDeserializacion("El campo '%s' está fuera de rango" % clave)
        return valor

    def _fecha(self, datos, clave):
        texto = self._texto(datos, clave, 40)
        try:
            fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            raise ErrorDeserializacion("Fecha inválida en '%s'" % clave)
        return fecha.isoformat()


# Códigos WMO que usa Open-Meteo para el estado del tiempo
DESCRIPCIONES_WMO = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Neblina", 48: "Neblina con escarcha",
    51: "Llovizna débil", 53: "Llovizna", 55: "Llovizna intensa",
    61: "Lluvia débil", 63: "Lluvia", 65: "Lluvia intensa",
    66: "Lluvia helada débil", 67: "Lluvia helada",
    71: "Nieve débil", 73: "Nieve", 75: "Nieve intensa", 77: "Granizo fino",
    80: "Chubascos débiles", 81: "Chubascos", 82: "Chubascos violentos",
    85: "Chubascos de nieve", 86: "Chubascos de nieve fuertes",
    95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta fuerte con granizo",
}


class DeserializadorClima(Deserializador):

    def ubicacion(self, json_geo):
        datos = self._objeto(json_geo, "geocodificación")
        resultados = datos.get("results")
        if not isinstance(resultados, list) or not resultados:
            raise CiudadNoEncontrada("No se encontró la ciudad consultada.")
        primero = self._objeto(resultados[0], "ubicación")
        return {
            "ciudad": self._texto(primero, "name", 80),
            "pais": self._texto(primero, "country", 80) if primero.get("country") else "Desconocido",
            "latitud": self._numero(primero, "latitude", -90, 90),
            "longitud": self._numero(primero, "longitude", -180, 180),
        }

    def clima(self, ubicacion, json_clima):
        datos = self._objeto(json_clima, "clima")
        actual = self._objeto(datos.get("current"), "clima actual")
        codigo = int(self._numero(actual, "weather_code", 0, 99))
        return Clima(
            ciudad=ubicacion["ciudad"],
            pais=ubicacion["pais"],
            latitud=ubicacion["latitud"],
            longitud=ubicacion["longitud"],
            temperatura=float(self._numero(actual, "temperature_2m", -90, 60)),
            humedad=int(self._numero(actual, "relative_humidity_2m", 0, 100)),
            codigo_tiempo=codigo,
            descripcion=DESCRIPCIONES_WMO.get(codigo, "Sin descripción"),
            viento=float(self._numero(actual, "wind_speed_10m", 0, 500)),
            fecha_observacion=self._fecha(actual, "time"),
            obtenido_en=ahora_iso(),
        )


class DeserializadorIndicadores(Deserializador):
    CODIGOS = ("dolar", "euro", "uf", "utm")

    def indicador(self, datos, codigo_esperado):
        datos = self._objeto(datos, codigo_esperado)
        codigo = self._texto(datos, "codigo", 20)
        if codigo != codigo_esperado:
            raise ErrorDeserializacion("El indicador no coincide con lo pedido")
        return Indicador(
            codigo=codigo,
            nombre=self._texto(datos, "nombre"),
            unidad=self._texto(datos, "unidad_medida", 20),
            # un tipo de cambio en 0 o negativo rompería los cálculos de pago
            valor=float(self._numero(datos, "valor", 0.0001, 10_000_000)),
            fecha=self._fecha(datos, "fecha"),
            obtenido_en=ahora_iso(),
        )

    def todos(self, json_api):
        datos = self._objeto(json_api, "indicadores")
        resultado = []
        for codigo in self.CODIGOS:
            if codigo not in datos:
                raise ErrorDeserializacion("La API no trajo el indicador %s" % codigo)
            resultado.append(self.indicador(datos[codigo], codigo))
        return resultado
