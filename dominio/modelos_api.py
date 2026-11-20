from dataclasses import dataclass


@dataclass
class Clima:
    ciudad: str
    pais: str
    latitud: float
    longitud: float
    temperatura: float
    humedad: int
    codigo_tiempo: int
    descripcion: str
    viento: float
    fecha_observacion: str
    obtenido_en: str


@dataclass
class Indicador:
    codigo: str
    nombre: str
    unidad: str
    valor: float
    fecha: str
    obtenido_en: str
