"""Pruebas sin internet (se simula la API con mocks).
Correr con:  python -m unittest -v"""

import unittest
from unittest.mock import MagicMock

import requests

from datos.almacen import Almacen
from datos.base_datos import ErrorBaseDatos, conectar_local
from datos.repositorios import RepositorioClima, RepositorioIndicadores
from seguridad.auth import ServicioAutenticacion
from seguridad.validaciones import ErrorValidacion, validar_ciudad
from servicios.api_cliente import ApiCliente, ErrorCliente, ErrorRed, ErrorServidor
from servicios.deserializadores import DeserializadorIndicadores, ErrorDeserializacion
from servicios.servicios_externos import ORIGEN_API, ORIGEN_LOCAL, ServicioClima

GEO = {"results": [{"name": "Concepción", "country": "Chile", "latitude": -36.82, "longitude": -73.04}]}
CLIMA = {"current": {"time": "2026-11-20T02:00", "temperature_2m": 11.5, "relative_humidity_2m": 80,
                     "weather_code": 3, "wind_speed_10m": 9.4}}
INDICADORES = {
    c: {"codigo": c, "nombre": c.upper(), "unidad_medida": "Pesos",
        "fecha": "2026-11-20T03:00:00.000Z", "valor": v}
    for c, v in (("dolar", 940.5), ("euro", 1020.3), ("uf", 40100.0), ("utm", 69000.0))
}


def respuesta(codigo, json=None, headers=None):
    r = MagicMock()
    r.status_code = codigo
    r.json.return_value = json if json is not None else {}
    r.headers = headers or {}
    return r


def cliente_con(*respuestas):
    sesion = MagicMock()
    sesion.headers = {}
    sesion.get.side_effect = list(respuestas)
    dormir = MagicMock()
    return ApiCliente(timeout=(3, 10), max_intentos=3, sesion=sesion, dormir=dormir), sesion, dormir


def almacen_local(prueba):
    almacen = Almacen(conectar_local(":memory:"))
    prueba.addCleanup(almacen.cerrar)
    return almacen


class TestApiCliente(unittest.TestCase):
    def test_siempre_manda_timeout(self):
        cliente, sesion, _ = cliente_con(respuesta(200, {"ok": True}))
        cliente.get_json("https://x.cl/api")
        self.assertEqual(sesion.get.call_args.kwargs["timeout"], (3, 10))
        self.assertNotIn("verify", sesion.get.call_args.kwargs)

    def test_404_no_se_reintenta(self):
        cliente, sesion, dormir = cliente_con(respuesta(404))
        with self.assertRaises(ErrorCliente):
            cliente.get_json("https://x.cl/no-existe")
        self.assertEqual(sesion.get.call_count, 1)
        dormir.assert_not_called()

    def test_500_se_reintenta_con_backoff(self):
        cliente, sesion, dormir = cliente_con(respuesta(500), respuesta(503), respuesta(500))
        with self.assertRaises(ErrorServidor):
            cliente.get_json("https://x.cl/api")
        self.assertEqual(sesion.get.call_count, 3)
        esperas = [c.args[0] for c in dormir.call_args_list]
        self.assertEqual(len(esperas), 2)
        self.assertLess(esperas[0], esperas[1])  # espera creciente

    def test_429_respeta_retry_after(self):
        cliente, _, dormir = cliente_con(respuesta(429, headers={"Retry-After": "7"}), respuesta(200, {"ok": 1}))
        self.assertEqual(cliente.get_json("https://x.cl/api"), {"ok": 1})
        dormir.assert_called_once_with(7.0)

    def test_sin_red_reintenta_y_luego_error_controlado(self):
        cliente, sesion, _ = cliente_con(*[requests.ConnectionError("sin wifi")] * 3)
        with self.assertRaises(ErrorRed):
            cliente.get_json("https://x.cl/api")
        self.assertEqual(sesion.get.call_count, 3)

    def test_timeout_y_despues_responde(self):
        cliente, _, _ = cliente_con(requests.Timeout(), respuesta(200, {"ok": 1}))
        self.assertEqual(cliente.get_json("https://x.cl/api"), {"ok": 1})

    def test_maximo_4_intentos(self):
        cliente = ApiCliente(timeout=5, max_intentos=50)
        self.assertEqual(cliente.max_intentos, 4)


class TestDeserializador(unittest.TestCase):
    def test_indicadores_validos(self):
        lista = DeserializadorIndicadores().todos(INDICADORES)
        self.assertEqual([i.codigo for i in lista], ["dolar", "euro", "uf", "utm"])

    def test_valor_negativo_o_texto_se_rechaza(self):
        malo = dict(INDICADORES, dolar=dict(INDICADORES["dolar"], valor=-1))
        with self.assertRaises(ErrorDeserializacion):
            DeserializadorIndicadores().todos(malo)
        malo = dict(INDICADORES, dolar=dict(INDICADORES["dolar"], valor="940"))
        with self.assertRaises(ErrorDeserializacion):
            DeserializadorIndicadores().todos(malo)


class TestPersistenciaYPlanB(unittest.TestCase):
    def test_idempotencia_clima(self):
        almacen = almacen_local(self)
        for _ in range(2):
            cliente, _, _ = cliente_con(respuesta(200, GEO), respuesta(200, CLIMA))
            ServicioClima(cliente, almacen).consultar("Concepción")
        self.assertEqual(RepositorioClima(almacen.local).contar(), 1)

    def test_idempotencia_indicadores(self):
        almacen = almacen_local(self)
        repo = RepositorioIndicadores(almacen.local)
        estados = [repo.guardar(i) for _ in range(2) for i in DeserializadorIndicadores().todos(INDICADORES)]
        self.assertEqual(repo.contar(), 4)
        self.assertEqual(estados.count("nuevo"), 4)

    def test_plan_b_sin_red(self):
        almacen = almacen_local(self)
        cliente, _, _ = cliente_con(respuesta(200, GEO), respuesta(200, CLIMA))
        resultado, _ = ServicioClima(cliente, almacen).consultar("Concepción")
        self.assertEqual(resultado.origen, ORIGEN_API)

        cliente, _, _ = cliente_con(*[requests.ConnectionError()] * 3)
        resultado, _ = ServicioClima(cliente, almacen).consultar("concepcion")
        self.assertEqual(resultado.origen, ORIGEN_LOCAL)
        self.assertTrue(resultado.datos.obtenido_en)

    def test_inyeccion_sql_no_rompe_nada(self):
        with self.assertRaises(ErrorValidacion):
            validar_ciudad("x'; DROP TABLE clima; --")


class TestAutenticacion(unittest.TestCase):
    def setUp(self):
        self.almacen = almacen_local(self)
        self.auth = ServicioAutenticacion(self.almacen, rondas=4)

    def test_password_no_queda_en_texto_plano(self):
        self.auth.registrar("gbustos", "Clave1234")
        guardado = self.almacen.local.fila("SELECT hash_password FROM usuarios")["hash_password"]
        self.assertNotIn("Clave1234", guardado)
        self.assertTrue(guardado.startswith("$2b$"))

    def test_mismo_password_distinto_hash(self):
        self.auth.registrar("usuario1", "Clave1234")
        self.auth.registrar("usuario2", "Clave1234")
        h1, h2 = [f["hash_password"] for f in self.almacen.local.filas("SELECT hash_password FROM usuarios")]
        self.assertNotEqual(h1, h2)  # por el salt

    def test_login(self):
        self.auth.registrar("gbustos", "Clave1234")
        self.assertIsNotNone(self.auth.autenticar("gbustos", "Clave1234"))
        self.assertIsNone(self.auth.autenticar("gbustos", "otra1234"))
        self.assertIsNone(self.auth.autenticar("noexiste", "Clave1234"))
        with self.assertRaises(ErrorValidacion):
            self.auth.autenticar("", "")

    def test_password_debil(self):
        with self.assertRaises(ErrorValidacion):
            self.auth.registrar("gbustos", "123")

    def test_usuario_duplicado(self):
        self.auth.registrar("gbustos", "Clave1234")
        with self.assertRaises(ErrorValidacion):
            self.auth.registrar("GBustos", "Clave1234")


class BaseQueSeCae:
    """Simula Supabase que se desconecta (WiFi cortado) a mitad de la sesión."""
    nombre = "Supabase"

    def __init__(self):
        self.real = conectar_local(":memory:")
        self.caida = False

    def _revisar(self):
        if self.caida:
            raise ErrorBaseDatos("sin red")

    def filas(self, sql, parametros=()):
        self._revisar()
        return self.real.filas(sql, parametros)

    def fila(self, sql, parametros=()):
        self._revisar()
        return self.real.fila(sql, parametros)

    def ejecutar(self, sql, parametros=()):
        return self.filas(sql, parametros)

    def ejecutar_varias(self, sentencias):
        self._revisar()
        # en la prueba la "nube" es SQLite, así que se usan las tablas SQLite
        from datos.esquema import TABLAS_LOCAL
        if sentencias and "CREATE TABLE" in sentencias[0][0]:
            sentencias = [(sql, ()) for sql in TABLAS_LOCAL]
        self.real.ejecutar_varias(sentencias)

    def cerrar(self):
        self.real.cerrar()


class TestAlmacenSupabase(unittest.TestCase):
    def setUp(self):
        self.remota = BaseQueSeCae()
        self.almacen = Almacen(conectar_local(":memory:"), "postgresql://x", conectar=lambda u, c: self.remota)
        self.addCleanup(self.almacen.local.cerrar)
        self.addCleanup(self.remota.real.cerrar)

    def test_escribe_en_las_dos_bases(self):
        ServicioAutenticacion(self.almacen, rondas=4).registrar("gbustos", "Clave1234")
        sql = "SELECT id FROM usuarios WHERE nombre_usuario = ?"
        self.assertIsNotNone(self.remota.real.fila(sql, ("gbustos",)))
        self.assertIsNotNone(self.almacen.local.fila(sql, ("gbustos",)))

    def test_si_supabase_se_cae_sigue_con_copia_local(self):
        auth = ServicioAutenticacion(self.almacen, rondas=4)
        auth.registrar("gbustos", "Clave1234")
        cliente, _, _ = cliente_con(respuesta(200, GEO), respuesta(200, CLIMA))
        ServicioClima(cliente, self.almacen).consultar("Concepción")

        self.remota.caida = True  # se corta el WiFi
        cliente, _, _ = cliente_con(*[requests.ConnectionError()] * 3)
        resultado, _ = ServicioClima(cliente, self.almacen).consultar("Concepción")
        self.assertEqual(resultado.origen, ORIGEN_LOCAL)
        self.assertFalse(self.almacen.en_linea)
        self.assertIsNotNone(auth.autenticar("gbustos", "Clave1234"))  # login sin internet


if __name__ == "__main__":
    unittest.main()
