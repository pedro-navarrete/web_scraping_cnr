# API Clave Catastral CNR

API REST construida con **FastAPI** y **Playwright** que realiza web scraping del portal del [CNR de El Salvador](https://www.e.cnr.gob.sv/ClaveCatastral/) para obtener la **clave catastral** de un inmueble a partir de su dirección.

El sitio del CNR es una SPA basada en ArcGIS/Esri, por lo que se requiere un navegador real (Chromium headless vía Playwright) en lugar de `requests`/`BeautifulSoup`.

---

## Requisitos

- **Python 3.11+**
- **pip**
- (Para producción) **Docker** y **Docker Compose**

---

## Uso en Windows 11 (desarrollo)

### 1. Clonar el repositorio

```bash
git clone https://github.com/pedro-navarrete/web_scraping_cnr.git
cd web_scraping_cnr
```

### 2. Crear y activar un entorno virtual

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Instalar Chromium para Playwright

```bash
playwright install chromium
```

### 5. Configurar variables de entorno (opcional)

```bash
copy .env.example .env
# Editar .env con tus valores si es necesario
```

### 6. Levantar la API

```bash
uvicorn app.main:app --reload
```

La API estará disponible en `http://localhost:8000`.  
Documentación interactiva (Swagger UI): `http://localhost:8000/docs`

---

## Uso en servidor Linux sin GUI (producción con Docker)

### 1. Construir la imagen

```bash
docker build -t web_scraping_cnr .
```

### 2. Ejecutar el contenedor

```bash
docker run -d \
  --name cnr_api \
  -p 8000:8000 \
  -e BROWSER_POOL_SIZE=3 \
  -e PAGE_TIMEOUT_MS=30000 \
  -e LOG_LEVEL=INFO \
  web_scraping_cnr
```

La imagen base `mcr.microsoft.com/playwright/python:v1.42.0-jammy` ya incluye todas las dependencias del sistema necesarias para Chromium en Linux headless.

---

## Endpoints

### `GET /health`

Verificación de que el servicio está en línea.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### `POST /api/clave-catastral`

Obtiene la clave catastral para la dirección indicada.

**Request:**

```bash
curl -X POST http://localhost:8000/api/clave-catastral \
  -H "Content-Type: application/json" \
  -d '{"direccion": "COLONIA LA SULTANA, AVENIDA LAS PALMERAS, NUMERO 27"}'
```

**Response 200:**

```json
{
  "clave_catastral": "0501U26-190",
  "direccion": "COLONIA LA SULTANA, AVENIDA LAS PALMERAS, NUMERO 27, ANTIGUO CUSCATLÁN, LA LIBERTAD ESTE, LA LIBERTAD",
  "propietario_siryc": "NO DISPONIBLE",
  "propietario_poseedor": "DISPONIBLE"
}
```

**Con Python / httpx:**

```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/clave-catastral",
    json={"direccion": "COLONIA LA SULTANA, AVENIDA LAS PALMERAS, NUMERO 27"},
)
print(response.json())
```

### Códigos de error

| Código | Significado |
|--------|-------------|
| `404`  | Dirección no encontrada en el CNR |
| `422`  | Body de la petición inválido (Pydantic) |
| `502`  | El popup no apareció o no se pudo parsear |
| `504`  | Timeout: el sitio del CNR no respondió |
| `500`  | Error interno inesperado |

---

## Variables de entorno

| Variable           | Default                                        | Descripción                              |
|--------------------|------------------------------------------------|------------------------------------------|
| `HOST`             | `0.0.0.0`                                      | Host de uvicorn                          |
| `PORT`             | `8000`                                         | Puerto de uvicorn                        |
| `BROWSER_POOL_SIZE`| `3`                                            | Número de contextos Playwright en el pool|
| `PAGE_TIMEOUT_MS`  | `30000`                                        | Timeout por operación en ms              |
| `HEADLESS`         | `true`                                         | Ejecutar Chromium en modo headless       |
| `CNR_URL`          | `https://www.e.cnr.gob.sv/ClaveCatastral/`    | URL del portal CNR                       |
| `LOG_LEVEL`        | `INFO`                                         | Nivel de logging (`DEBUG`, `INFO`, etc.) |

---

## Pool de navegadores

La aplicación mantiene un pool de `BROWSER_POOL_SIZE` contextos de Playwright reutilizables:

- **Una sola instancia de Chromium** durante todo el ciclo de vida de la app.
- Los contextos se crean al inicio (lifespan de FastAPI) y se reutilizan entre peticiones.
- Si un contexto se corrompe durante una petición, se descarta automáticamente y se crea uno nuevo.
- Al apagar el servidor, todos los contextos y el navegador se cierran limpiamente.

---

## Tests

```bash
pytest tests/
```

Los tests de `tests/test_health.py` verifican el endpoint `/health` y la validación básica del endpoint `/api/clave-catastral` sin necesidad de conexión al CNR.

---

## Troubleshooting

### `playwright install chromium` falla en Linux

Si no usas Docker, instala las dependencias del sistema:

```bash
playwright install-deps chromium
playwright install chromium
```

### El scraping falla con `TimeoutCNRError`

- Aumentar `PAGE_TIMEOUT_MS` (ej. `60000`).
- Verificar que el servidor tiene acceso a `https://www.e.cnr.gob.sv/`.

### Los selectores no funcionan

El sitio del CNR usa ArcGIS/Esri, cuyo HTML puede cambiar entre actualizaciones.
Los selectores están definidos como constantes en la parte superior de `app/scraper.py`.
Inspeccionar el sitio con DevTools y actualizar los selectores según sea necesario.