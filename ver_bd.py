"""Muestra el contenido de las bases (Supabase y copia local) para la revisión en sala.
Uso: python ver_bd.py"""

import config
from datos.base_datos import ErrorBaseDatos, conectar_local, conectar_supabase
from datos.esquema import inicializar

# consultas fijas, sin armar SQL con texto
CONTEOS = [
    ("usuarios", "SELECT COUNT(*) AS total FROM usuarios"),
    ("clima", "SELECT COUNT(*) AS total FROM clima"),
    ("indicadores", "SELECT COUNT(*) AS total FROM indicadores"),
    ("proyectos", "SELECT COUNT(*) AS total FROM proyectos"),
    ("empleados", "SELECT COUNT(*) AS total FROM empleados"),
]


def mostrar(bd):
    print("\n==================== %s ====================" % bd.nombre.upper())
    print("--- Filas por tabla ---")
    for tabla, consulta in CONTEOS:
        print("  %-12s %d" % (tabla, bd.fila(consulta)["total"]))

    print("\n--- Usuarios (solo se guarda el hash bcrypt) ---")
    for u in bd.filas("SELECT nombre_usuario, hash_password, creado_en FROM usuarios ORDER BY id"):
        print("  %-15s %s  (creado %s)" % (u["nombre_usuario"], u["hash_password"], u["creado_en"]))

    print("\n--- Clima guardado ---")
    for c in bd.filas("SELECT ciudad, temperatura, descripcion, obtenido_en FROM clima ORDER BY obtenido_en DESC"):
        print("  %-15s %5.1f °C  %-22s obtenido_en %s" % (
            c["ciudad"], c["temperatura"], c["descripcion"], c["obtenido_en"]))

    print("\n--- Indicadores guardados ---")
    for i in bd.filas("SELECT codigo, valor, fecha, obtenido_en FROM indicadores ORDER BY codigo, fecha"):
        print("  %-6s %12.2f  fecha %s  obtenido_en %s" % (
            i["codigo"], i["valor"], i["fecha"][:10], i["obtenido_en"]))


def main():
    remota = conectar_supabase(config.SUPABASE_DB_URL, config.SUPABASE_CA_CERT)
    if remota:
        try:
            inicializar(remota)
            mostrar(remota)
        except ErrorBaseDatos as error:
            print("\nSupabase:", error.mensaje_usuario)
        finally:
            remota.cerrar()
    else:
        print("\nSupabase: sin conexión (o SUPABASE_DB_URL vacío en .env).")

    local = conectar_local(config.DB_PATH)
    inicializar(local)
    mostrar(local)
    local.cerrar()


if __name__ == "__main__":
    config.configurar_logs()
    main()
