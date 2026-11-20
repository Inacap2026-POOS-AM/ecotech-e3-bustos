"""EcoTech Solutions - Entrega 3 (TI3021)
Consumo seguro de APIs de clima (Open-Meteo) e indicadores económicos (mindicador.cl)
con login, reintentos, persistencia en Supabase y Plan B con copia local (SQLite).

Uso:  python main.py
"""

import logging
import sys
from getpass import getpass

import config
from datos.almacen import Almacen
from datos.base_datos import conectar_local
from seguridad.auth import ServicioAutenticacion
from seguridad.validaciones import ErrorValidacion, validar_moneda, validar_monto
from servicios.api_cliente import ApiCliente
from servicios.servicios_externos import (ORIGEN_API, ORIGEN_LOCAL, ServicioClima,
                                          ServicioIndicadores, antiguedad)

log = logging.getLogger("ecotech")
MAX_INTENTOS_LOGIN = 3


def pesos(valor):
    return "$" + format(round(valor), ",").replace(",", ".")


def tasa(valor):
    """940.5 -> $940,50 (formato chileno con 2 decimales)"""
    texto = format(valor, ",.2f").replace(",", "X").replace(".", ",").replace("X", ".")
    return "$" + texto


def dinero(valor, moneda):
    if moneda == "CLP":
        return pesos(valor) + " CLP"
    return "%s %s" % (format(valor, ",.2f"), moneda)


class App:
    def __init__(self):
        print("Conectando a Supabase...")
        self.almacen = Almacen(conectar_local(config.DB_PATH),
                               config.SUPABASE_DB_URL, config.SUPABASE_CA_CERT)
        self.mostrar_estado_bd()
        cliente = ApiCliente(
            timeout=config.HTTP_TIMEOUT,
            max_intentos=config.HTTP_MAX_INTENTOS,
            backoff_base=config.HTTP_BACKOFF_BASE,
            espera_maxima=config.HTTP_ESPERA_MAXIMA,
        )
        self.auth = ServicioAutenticacion(self.almacen)
        self.clima = ServicioClima(cliente, self.almacen)
        self.indicadores = ServicioIndicadores(cliente, self.almacen)
        self.usuario = None

    def mostrar_estado_bd(self):
        if self.almacen.en_linea:
            print("Base de datos: Supabase conectado (con copia local para el Plan B).")
        elif config.SUPABASE_DB_URL:
            print("Base de datos: Supabase no disponible, se trabaja con la copia local.")
        else:
            print("Base de datos: SUPABASE_DB_URL vacío en .env, se trabaja solo con la copia local.")

    # ---------------- autenticación ----------------

    def registrar(self):
        print("\n--- Registro de usuario ---")
        print("La contraseña debe tener mínimo 8 caracteres, con letras y números.")
        nombre = input("Usuario: ")
        password = getpass("Contraseña: ")
        repetir = getpass("Repita la contraseña: ")
        if password != repetir:
            print("Las contraseñas no coinciden.")
            return
        try:
            usuario = self.auth.registrar(nombre, password)
            print("Usuario '%s' creado. Ya puede iniciar sesión." % usuario.nombre_usuario)
        except ErrorValidacion as error:
            print("No se pudo registrar:", error)

    def iniciar_sesion(self):
        for intento in range(1, MAX_INTENTOS_LOGIN + 1):
            print("\n--- Inicio de sesión (intento %d de %d) ---" % (intento, MAX_INTENTOS_LOGIN))
            nombre = input("Usuario: ")
            password = getpass("Contraseña: ")
            try:
                usuario = self.auth.autenticar(nombre, password)
            except ErrorValidacion as error:
                print(error)
                continue
            if usuario:
                self.usuario = usuario
                print("Bienvenido/a, %s." % usuario.nombre_usuario)
                return True
            print("Usuario o contraseña incorrectos.")
        print("Demasiados intentos fallidos.")
        return False

    # ---------------- funcionalidades ----------------

    def mostrar_clima(self, resultado):
        clima = resultado.datos
        if clima is None:
            print("  Sin datos disponibles:", resultado.aviso or "no hay información guardada.")
            return
        if resultado.origen == ORIGEN_LOCAL:
            print("  [PLAN B] %s Se muestran datos guardados localmente." % resultado.aviso)
            print("  obtenido_en: %s (%s)" % (clima.obtenido_en, antiguedad(clima.obtenido_en)))
        print("  %s, %s | %.1f °C | humedad %d%% | %s | viento %.1f km/h | hora local %s" % (
            clima.ciudad, clima.pais, clima.temperatura, clima.humedad,
            clima.descripcion, clima.viento, clima.fecha_observacion))
        if clima.codigo_tiempo >= 61 or clima.viento >= 50:
            print("  ! Atención: condiciones que pueden retrasar trabajos en terreno.")

    def consultar_clima(self):
        ciudad = input("\nCiudad a consultar: ")
        try:
            resultado, _ = self.clima.consultar(ciudad)
        except ErrorValidacion as error:
            print(error)
            return
        self.mostrar_clima(resultado)

    def clima_proyectos(self):
        print("\n--- Clima en las ciudades de los proyectos ---")
        conteo = {"nuevo": 0, "actualizado": 0}
        for proyecto in self.almacen.proyectos():
            print("\n" + proyecto.nombre)
            resultado, estado = self.clima.consultar(proyecto.ciudad)
            self.mostrar_clima(resultado)
            if estado:
                conteo[estado] += 1
        return conteo

    def mostrar_indicadores(self, resultado):
        if resultado.datos is None:
            print("  Sin datos disponibles:", resultado.aviso or "no hay información guardada.")
            return
        if resultado.origen == ORIGEN_LOCAL:
            print("  [PLAN B] %s Se muestran datos guardados localmente." % resultado.aviso)
        for indicador in resultado.datos.values():
            linea = "  %-32s %s  (fecha %s)" % (indicador.nombre, tasa(indicador.valor), indicador.fecha[:10])
            if resultado.origen == ORIGEN_LOCAL:
                linea += "  obtenido_en %s (%s)" % (indicador.obtenido_en, antiguedad(indicador.obtenido_en))
            print(linea)

    def consultar_indicadores(self):
        print("\n--- Indicadores económicos ---")
        resultado, _ = self.indicadores.actualizar()
        self.mostrar_indicadores(resultado)

    def calcular_pagos(self):
        print("\n--- Pago de trabajadores en moneda del país del proyecto ---")
        resultado, _ = self.indicadores.actualizar()
        if resultado.origen == ORIGEN_LOCAL:
            print("  [PLAN B] %s Se usarán los últimos valores guardados." % resultado.aviso)
        elif resultado.origen != ORIGEN_API:
            print("  No hay tipos de cambio disponibles; solo se muestran montos en CLP.")
        for proyecto in self.almacen.proyectos():
            print("\n%s" % proyecto)
            for empleado in proyecto.empleados:
                monto, indicador = self.indicadores.convertir(
                    empleado.sueldo_clp, proyecto.moneda, resultado.datos)
                if monto is None:
                    texto = "tipo de cambio no disponible"
                else:
                    texto = dinero(monto, proyecto.moneda)
                    if indicador:
                        texto += "  (1 %s = %s, %s)" % (proyecto.moneda, tasa(indicador.valor),
                                                        indicador.fecha[:10])
                print("  %-18s %s -> %s" % (empleado.nombre, pesos(empleado.sueldo_clp), texto))

    def convertir_monto(self):
        try:
            monto = validar_monto(input("\nMonto en CLP: "))
            moneda = validar_moneda(input("Moneda destino (USD, EUR, UF, UTM): "))
        except ErrorValidacion as error:
            print(error)
            return
        resultado, _ = self.indicadores.actualizar()
        if resultado.origen == ORIGEN_LOCAL:
            print("  [PLAN B] %s Se usa el último valor guardado." % resultado.aviso)
        convertido, indicador = self.indicadores.convertir(monto, moneda, resultado.datos)
        if convertido is None:
            print("  No hay tipo de cambio disponible para %s." % moneda)
            return
        print("  %s = %s" % (pesos(monto), dinero(convertido, moneda)))
        if indicador and resultado.origen == ORIGEN_LOCAL:
            print("  obtenido_en: %s (%s)" % (indicador.obtenido_en, antiguedad(indicador.obtenido_en)))

    def sincronizar(self):
        """Pensada para la prueba de idempotencia: correrla 2 veces no duplica registros."""
        print("\n=== Sincronización ===")
        self.almacen.reconectar()
        self.mostrar_estado_bd()
        antes, _ = self.almacen.conteos()
        conteo_clima = self.clima_proyectos()
        print("\nIndicadores:")
        resultado, conteo_ind = self.indicadores.actualizar()
        self.mostrar_indicadores(resultado)
        despues, base = self.almacen.conteos()
        print("\nResumen (filas en %s):" % base)
        print("  Clima       -> nuevos: %d, actualizados: %d | filas en tabla: %d -> %d" % (
            conteo_clima["nuevo"], conteo_clima["actualizado"], antes[0], despues[0]))
        print("  Indicadores -> nuevos: %d, actualizados: %d | filas en tabla: %d -> %d" % (
            conteo_ind["nuevo"], conteo_ind["actualizado"], antes[1], despues[1]))

    # ---------------- menús ----------------

    def menu_principal(self):
        opciones = {
            "1": ("Consultar clima de una ciudad", self.consultar_clima),
            "2": ("Clima de las ciudades de los proyectos", self.clima_proyectos),
            "3": ("Indicadores económicos (dólar, euro, UF, UTM)", self.consultar_indicadores),
            "4": ("Calcular pagos por proyecto en moneda local", self.calcular_pagos),
            "5": ("Convertir un monto en CLP", self.convertir_monto),
            "6": ("Sincronizar todo (clima + indicadores)", self.sincronizar),
        }
        while self.usuario:
            print("\n===== EcoTech Solutions | usuario: %s =====" % self.usuario.nombre_usuario)
            for clave, (texto, _) in opciones.items():
                print("%s. %s" % (clave, texto))
            print("0. Cerrar sesión")
            opcion = input("Opción: ").strip()
            if opcion == "0":
                self.usuario = None
            elif opcion in opciones:
                opciones[opcion][1]()
            else:
                print("Opción inválida.")

    def ejecutar(self):
        print("=== EcoTech Solutions - Integración de servicios externos ===")
        while True:
            print("\n1. Iniciar sesión\n2. Registrar usuario\n0. Salir")
            opcion = input("Opción: ").strip()
            if opcion == "1":
                if self.iniciar_sesion():
                    self.menu_principal()
            elif opcion == "2":
                self.registrar()
            elif opcion == "0":
                break
            else:
                print("Opción inválida.")
        self.almacen.cerrar()
        print("Hasta luego.")


def main():
    config.configurar_logs()
    try:
        App().ejecutar()
    except KeyboardInterrupt:
        print("\nPrograma interrumpido por el usuario.")
    except Exception:
        # el detalle completo queda en logs/ecotech.log, al usuario no se le muestra la traza
        log.exception("Error inesperado")
        print("\nOcurrió un error inesperado. El detalle quedó registrado en logs/ecotech.log.")
        sys.exit(1)


if __name__ == "__main__":
    main()
