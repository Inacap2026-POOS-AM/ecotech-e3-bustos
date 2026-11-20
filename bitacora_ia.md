# Bitácora de IA – Entrega 3

**Herramienta usada:** Claude (Anthropic), como asistente de programación.
**Uso:** le pasé la guía de la E3 y la estructura del repo de la E2, y le pedí que generara el cliente de API, los deserializadores, la persistencia y el login. Después revisé el código buscando las 5 señales de riesgo que vimos en clase y decidí qué aceptar, qué cambiar y qué descartar.

> Regla que seguí: no subir nada que no pueda explicar. Si no entendía una parte, la pregunté o la reescribí más simple.

---

## 1. Auditoría de las 5 señales de riesgo

Revisé el código a mano y además con búsquedas en todo el proyecto:

| # | Señal de riesgo | Cómo la busqué | Resultado | Decisión |
|---|---|---|---|---|
| 1 | **f-strings o concatenación en SQL** | `grep -rn "execute(f" .` y revisé cada `execute` en `datos/` | 0 casos. Todas las consultas usan `?` | **Aceptado**. Lo comprobé con una prueba: la ciudad `x'; DROP TABLE clima; --` se rechaza en la validación y aunque pasara, iría como parámetro y no como SQL |
| 2 | **`verify=False`** | `grep -rn "verify" .` y revisé el SSL de la conexión a Supabase | 0 casos. `requests` verifica el certificado por defecto. Para Supabase se usa `ssl.create_default_context(cafile=...)` con el certificado de la CA de Supabase | **Aceptado**. Desactivar la verificación deja la conexión abierta a un man-in-the-middle: alguien en la misma red podría cambiar el tipo de cambio que llega o leer la clave de la base. Supabase firma con su propia CA, por eso hay que darle su certificado en vez de apagar la verificación |
| 3 | **`except: pass`** | `grep -rnE "except *:" .` | 0 casos. Todos los `except` capturan excepciones concretas (`requests.Timeout`, `ConnectionError`, `ErrorApi`, `ErrorValidacion`) y hacen algo: reintentar, registrar en el log o pasar al Plan B | **Aceptado**. El único `except Exception` está en `main()` y **no** es silencioso: guarda la traza en `logs/ecotech.log` y muestra un mensaje genérico |
| 4 | **Llamadas sin `timeout`** | Revisé todas las llamadas `.get(` a la red y la conexión a la base | Hay una sola llamada HTTP en todo el proyecto (`ApiCliente.get_json`) y lleva `timeout=self.timeout`. El constructor tira error si se crea sin timeout. La conexión a Supabase también lleva `timeout=5` (si se corta el WiFi una consulta no queda colgada) | **Aceptado**. Lo dejé en un solo lugar a propósito para no olvidarlo en otra parte. Hay una prueba (`test_siempre_manda_timeout`) que lo verifica |
| 5 | **Librerías que no existen en PyPI** | Revisé cada import y busqué cada paquete con `pip index versions <paquete>` | `requests` (2.34.2), `bcrypt` (5.0.0), `python-dotenv` (1.2.4) y `pg8000` (1.31.6) existen y son las oficiales. El resto (`sqlite3`, `json`, `logging`, `getpass`, `email.utils`) es librería estándar de Python | **Aceptado**. Ojo con `python-dotenv`: el import es `dotenv` pero el paquete se instala como `python-dotenv`. Existe un paquete llamado solo `dotenv` que no es el mismo |

---

## 2. Riesgos que revisé y ajustes al código

| Parte | Riesgo de la versión simple | Ajuste y por qué |
|---|---|---|
| Número de intentos | Leer `HTTP_MAX_INTENTOS` del `.env` tal cual. Si alguien pone 50, la app queda pegada reintentando | **Modificado**: se limita entre 1 y 4 en `config.py` y otra vez en `ApiCliente`. La guía pide máximo 3 a 4 |
| `Retry-After` | Esperar lo que diga el servidor sin límite. Si manda `Retry-After: 3600` el programa se congela una hora | **Modificado**: tope de 30 s (`HTTP_ESPERA_MAXIMA`). También acepta el formato fecha, no solo segundos |
| Logs | Registrar en el log la URL completa con parámetros | **Modificado**: `_url_segura()` deja solo host y ruta. Si más adelante se usa una API con llave en la URL (`?appid=...`), la llave no queda en el log |
| Errores al usuario | Mostrar `str(error)` de `requests`, que trae la URL, el puerto y detalles internos | **Modificado**: cada excepción propia tiene un `mensaje_usuario` corto ("No hay conexión con el servicio externo"). Lo técnico va solo al log |
| Contraseñas | Usar bcrypt sin revisar el largo | **Modificado**: bcrypt solo usa los primeros 72 bytes, así que una clave más larga se rechaza en vez de cortarla sin avisar. También agregué mínimo 8 caracteres con letras y números |
| Login | Decir "el usuario no existe" o "contraseña incorrecta" por separado | **Modificado**: siempre el mismo mensaje, y si el usuario no existe igual se compara contra un hash falso para que tarde lo mismo. Así no se puede averiguar qué usuarios existen |
| Deserialización | Leer `datos["valor"]` directo | **Modificado**: se revisa tipo y rango. Detalle: en Python `True` cuenta como número (`isinstance(True, int)` da `True`), así que se descarta aparte. Un tipo de cambio en 0 haría dividir por cero al calcular pagos |
| Idempotencia | Con un `INSERT` normal se duplican filas en cada ejecución | **Modificado**: `UNIQUE` en las tablas + `INSERT ... ON CONFLICT DO UPDATE`. Lo probé corriendo la sincronización dos veces: la segunda da "nuevos: 0" |

| Conexión a Supabase | Si se pierde la conexión con la base, el programa se cae con una excepción de `pg8000` | **Modificado**: `Almacen` atrapa el error, marca Supabase como caído y sigue con la copia local SQLite. La opción 6 intenta reconectar |
| Login sin internet | Si el usuario solo existe en Supabase, sin red no se puede iniciar sesión | **Modificado**: al conectar se copian los usuarios (solo el hash) entre Supabase y la copia local |
| Tablas en Supabase | Supabase publica las tablas por su API REST; sin RLS cualquiera con la anon key podría leer los hashes | **Modificado**: se activa RLS en todas las tablas. El script entra directo a PostgreSQL como dueño, así que no le afecta |
| Logs de la base | Registrar el error de conexión con la URL completa | **Modificado**: la URL de Supabase trae la contraseña, así que en el log solo va el host |

## 3. Cosas que descarté

| Propuesta | Por qué la descarté |
|---|---|
| Usar `HTTPAdapter` + `urllib3.Retry` para los reintentos automáticos | Funciona, pero esconde la lógica y no deja claro qué códigos se reintentan y cuáles no. Preferí escribir el ciclo de reintentos a mano para poder explicar cada caso (4xx / 429 / 5xx / red) |
| Usar OpenWeatherMap para el clima | Pide registrarse y una API key. Open-Meteo entrega los mismos datos sin llave, así no hay secretos que proteger. Igual dejé `API_KEY_CLIMA` en el `.env.example` por si se cambia |
| Mostrar la traza completa (`traceback.print_exc()`) para "ayudar a depurar" | Expone rutas, nombres de archivos y estructura interna. Se dejó solo en el log |
| Usar `psycopg2`/`psycopg` para PostgreSQL | En Windows necesita una versión compilada para cada versión de Python y yo tengo Python 3.15. `pg8000` es 100% Python, oficial en PyPI y no necesita instalar nada más |
| Usar Supabase solo por su API REST con la anon key | Habría que dejar las tablas abiertas (o crear políticas) para que la anon key pueda leer usuarios. Con conexión directa a PostgreSQL puedo usar consultas parametrizadas, `UNIQUE` y `ON CONFLICT` igual que en la base local |
| Guardar la contraseña con `hashlib.sha256` | SHA-256 es muy rápido, así que es fácil de atacar por fuerza bruta, y sin salt dos usuarios con la misma clave tienen el mismo hash. bcrypt es lento a propósito y trae el salt incluido |

## 4. Cómo lo verifiqué

- 20 pruebas unitarias (`python -m unittest -v`) que simulan la API: 404 sin reintento, 500 con 3 intentos y espera creciente, 429 con `Retry-After`, sin red, idempotencia, Plan B, hash distinto para la misma clave, login correcto e incorrecto.
- Probé el programa completo contra un PostgreSQL real y una API falsa local: dos sincronizaciones seguidas (no duplica), URL con 404 (pasa a Plan B), base apagada a mitad de la sesión (sigue con la copia local) y partir sin base ni API (login y Plan B funcionan).
- Revisé la tabla `usuarios`: solo hay hashes `$2b$12$...`.

## 5. Conclusión

La IA ahorró tiempo en la estructura y en lo repetitivo, pero varias cosas venían "funcionando" sin estar bien pensadas para seguridad: límites de espera, qué se muestra en los errores, el largo de la clave en bcrypt y la duplicación de registros. Esas fueron las partes donde más tuve que revisar y decidir, además de cómo usar Supabase sin perder el Plan B cuando no hay internet.
