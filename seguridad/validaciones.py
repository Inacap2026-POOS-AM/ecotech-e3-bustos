"""Validación de todo lo que escribe el usuario antes de usarlo."""

import re
import unicodedata


class ErrorValidacion(Exception):
    """Dato ingresado por el usuario que no cumple el formato esperado."""


PATRON_USUARIO = re.compile(r"^[a-zA-Z0-9_.]{3,30}$")
# letras (con tildes y ñ), espacios, guion, punto y apóstrofe. Nada de símbolos raros.
PATRON_CIUDAD = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñÀ-ÿ' .\-]{2,60}$")

MONEDAS = {
    "CLP": None,       # peso chileno, no necesita conversión
    "USD": "dolar",
    "EUR": "euro",
    "UF": "uf",
    "UTM": "utm",
}


def validar_usuario(nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorValidacion("El usuario no puede estar vacío.")
    if not PATRON_USUARIO.match(nombre):
        raise ErrorValidacion("Usuario inválido: 3 a 30 caracteres, solo letras, números, punto o guion bajo.")
    return nombre.lower()


def validar_password_nueva(password):
    if not password or not password.strip():
        raise ErrorValidacion("La contraseña no puede estar vacía.")
    if len(password) < 8:
        raise ErrorValidacion("La contraseña debe tener al menos 8 caracteres.")
    # bcrypt solo usa los primeros 72 bytes, más largo daría una falsa sensación de seguridad
    if len(password.encode("utf-8")) > 72:
        raise ErrorValidacion("La contraseña es demasiado larga (máximo 72 bytes).")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ErrorValidacion("La contraseña debe tener al menos una letra y un número.")
    return password


def validar_ciudad(ciudad):
    ciudad = " ".join((ciudad or "").split())
    if not ciudad:
        raise ErrorValidacion("Debe ingresar una ciudad.")
    if not PATRON_CIUDAD.match(ciudad):
        raise ErrorValidacion("Ciudad inválida: use solo letras y espacios (2 a 60 caracteres).")
    return ciudad


def validar_moneda(moneda):
    moneda = (moneda or "").strip().upper()
    if moneda not in MONEDAS:
        raise ErrorValidacion("Moneda no soportada. Opciones: " + ", ".join(MONEDAS))
    return moneda


def validar_monto(texto):
    texto = (texto or "").strip().replace(".", "").replace("$", "")
    if not texto.isdigit():
        raise ErrorValidacion("El monto debe ser un número entero positivo en pesos.")
    monto = int(texto)
    if monto <= 0 or monto > 1_000_000_000:
        raise ErrorValidacion("El monto debe estar entre 1 y 1.000.000.000 CLP.")
    return monto


def normalizar(texto):
    """'Concepción' -> 'concepcion', para buscar en la base sin depender de tildes."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())
