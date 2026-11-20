# EcoTech Solutions – Entrega 3 (TI3021)

**Script de consumo seguro de APIs y resiliencia**
Autor: Gonzalo Bustos Fernández · Rama: `e3/bustos`

Extensión del sistema de EcoTech (empleados y proyectos de la E2) que integra dos servicios externos:

| Necesidad | API | ¿Pide llave? |
|---|---|---|
| Clima para planificar proyectos (temperatura, humedad, estado del tiempo, viento) | [Open-Meteo](https://open-meteo.com/) (geocoding + forecast) | No |
| Tipo de cambio para pagar trabajadores en otros países (dólar, euro, UF, UTM) | [mindicador.cl](https://mindicador.cl/) | No |

**Base de datos:** Supabase (PostgreSQL en la nube) como base principal, conectada con `pg8000` y SSL verificado. Además, todo se guarda en una **copia local SQLite** (`ecotech_local.db`), porque si se corta el WiFi tampoco se llega a Supabase: esa copia es la que usa el Plan B.

## Cómo ejecutar

```bash
python -m venv venv
venv\Scripts\activate            # en Windows (en Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # en Linux/Mac: cp .env.example .env
python main.py
```
(o doble clic en `instalar.bat`)

**Configurar Supabase:** en el `.env` pegar en `SUPABASE_DB_URL` el URI de *Connect → Session pooler* del proyecto, y dejar el certificado en `certs/prod-ca-2021.crt` (ver `certs/LEEME.txt`). Las tablas se crean solas la primera vez. Si `SUPABASE_DB_URL` queda vacío o no hay internet, el programa funciona igual solo con la copia local.

La primera vez hay que **registrar un usuario** (opción 2) y después iniciar sesión. Sin login no se puede usar ninguna función.

Pruebas automáticas (no necesitan internet, la API se simula):

```bash
python -m unittest -v
```

## Estructura

```
main.py                       menú, login y flujo de la app
config.py                     lee el .env (URLs, timeouts, intentos)
servicios/api_cliente.py      cliente HTTP: timeout, reintentos, backoff, manejo por código
servicios/deserializadores.py clases que validan y convierten el JSON a objetos
servicios/servicios_externos.py  lógica de clima / indicadores + Plan B
datos/base_datos.py           conexión a Supabase (pg8000 + SSL) y a la copia local SQLite
datos/esquema.py              tablas de las dos bases (con UNIQUE para no duplicar)
datos/repositorios.py         consultas SQL, todas parametrizadas
datos/almacen.py              escribe en Supabase + copia local, lee de Supabase o de la copia
certs/                        certificado de la CA de Supabase
seguridad/auth.py             registro y login con bcrypt
seguridad/validaciones.py     validación de entradas del usuario
dominio/                      clases de la E1/E2 (Persona, Empleado, Proyecto, etc.)
tests/                        pruebas unitarias
ver_bd.py                     muestra las tablas (para la revisión en sala)
instalar.bat                  instalación rápida en Windows
bitacora_ia.md                auditoría del código generado con IA
```

## Qué cumple cada requisito

**Cliente de API (`servicios/api_cliente.py`)**
- Todas las peticiones llevan `timeout=(conexión, lectura)`. El constructor ni siquiera acepta crearse sin timeout.
- `4xx` → no se reintenta (404, 401, 403, etc. son errores de la petición, repetirla no cambia nada).
- `429` → se reintenta esperando lo que diga `Retry-After` (segundos o fecha), con tope de 30 s.
- `5xx`, timeout y caída de red → se reintenta con backoff exponencial (1 s, 2 s, 4 s + un poco de azar).
- Máximo 3 intentos por defecto; aunque en el `.env` se ponga más, se limita a 4.

**Plan B (degradación controlada)**
Si la API no responde (sin WiFi, URL mala, servidor caído), se busca el último dato guardado (primero en Supabase y, si tampoco responde, en la copia local SQLite) y se muestra con su `obtenido_en` y cuánto tiempo tiene ("hace 2 h 10 min"). Si Supabase se cae en medio de la sesión, el programa lo detecta, avisa y sigue con la copia local; el login también funciona sin internet porque los hashes están copiados en la base local. Si no hay nada guardado se avisa con un mensaje normal. Nunca se muestra una traza de error; el detalle técnico queda en `logs/ecotech.log`.

**Deserialización y persistencia**
`DeserializadorClima` y `DeserializadorIndicadores` revisan que cada campo exista, sea del tipo correcto y esté en un rango lógico (ej. humedad entre 0 y 100, tipo de cambio mayor a 0) antes de crear el objeto. Todo el SQL usa `?`, sin f-strings ni concatenación.

**Idempotencia**
Las tablas tienen `UNIQUE (ciudad, país, fecha_observacion)` y `UNIQUE (codigo, fecha)` y se guarda con `INSERT ... ON CONFLICT DO UPDATE`. Si el script corre dos veces, el mismo dato se actualiza en vez de duplicarse. La opción 6 (sincronizar) muestra cuántas filas había antes y después.

**Seguridad**
- Contraseñas con `bcrypt` (salt aleatorio por usuario, 12 rondas). En la tabla `usuarios` solo queda el hash `$2b$12$...`.
- Validación de usuario, contraseña (mín. 8, letras y números), ciudad (solo letras) y moneda (lista cerrada).
- Login con 3 intentos y el mismo mensaje si falla el usuario o la clave.
- `.env` fuera del repo, solo se sube `.env.example`. La URL de Supabase (que trae la clave) nunca se escribe en los logs.
- Conexión a Supabase con SSL verificado contra el certificado de la CA de Supabase (nunca se desactiva la verificación).
- RLS activado en las tablas de Supabase: su API REST pública no puede leerlas (por ejemplo, los hashes).

## Pruebas en vivo (C14)

| Prueba | Qué hacer | Qué debería pasar |
|---|---|---|
| 1. Ejecución consecutiva | Correr `python main.py`, opción 6, salir y repetir | La segunda vez: "nuevos: 0, actualizados: N" y las filas de la tabla no aumentan |
| 2. Corte de red | Desconectar WiFi, opción 1, 3 o 4 | Mensaje `[PLAN B]` con datos guardados y su `obtenido_en`, sin caerse |
| 3. URL inválida | En `.env` cambiar `URL_INDICADORES=https://mindicador.cl/apiXX` | Error 404 detectado sin reintentos y se pasa al Plan B |
| 4. Base de datos | `python ver_bd.py` (muestra Supabase y la copia local) o el Table Editor de Supabase | Solo hashes bcrypt, ninguna contraseña legible |
