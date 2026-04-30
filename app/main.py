"""
Aplicación FastAPI principal.

Ciclo de vida (lifespan):
  - startup: inicializa el pool de navegadores Playwright.
  - shutdown: cierra el pool limpiamente.

Rutas:
  - GET  /           → bienvenida / redirect a /docs
  - GET  /health     → {"status": "ok"}
  - POST /api/clave-catastral → scraping del CNR
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.browser_pool import BrowserPool
from app.config import settings
from app.exceptions import (
    DireccionNoEncontradaError,
    PopupNoDisponibleError,
    TimeoutCNRError,
)
from app.models import ClaveCatastralRequest, ClaveCatastralResponse
from app.scraper import scrape_clave_catastral

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pool global de navegadores
# ---------------------------------------------------------------------------
pool = BrowserPool(size=settings.browser_pool_size)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Gestiona el ciclo de vida del pool de navegadores."""
    await pool.start()
    yield
    await pool.stop()


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------
app = FastAPI(
    title="API Clave Catastral CNR",
    description=(
        "API REST que realiza web scraping del portal del CNR de El Salvador "
        "para obtener la clave catastral a partir de una dirección."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Manejadores de errores personalizados
# ---------------------------------------------------------------------------
@app.exception_handler(DireccionNoEncontradaError)
async def handler_404(request: Request, exc: DireccionNoEncontradaError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc) or "Dirección no encontrada en el CNR."},
    )


@app.exception_handler(TimeoutCNRError)
async def handler_504(request: Request, exc: TimeoutCNRError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=504,
        content={"detail": str(exc) or "El sitio del CNR no respondió a tiempo."},
    )


@app.exception_handler(PopupNoDisponibleError)
async def handler_502(request: Request, exc: PopupNoDisponibleError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc) or "No se pudo obtener la información catastral."},
    )


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirige a la documentación automática de FastAPI."""
    return RedirectResponse(url="/docs")


@app.get("/health", summary="Health check")
async def health() -> dict[str, Any]:
    """Verifica que el servicio está en línea."""
    return {"status": "ok"}


@app.post(
    "/api/clave-catastral",
    response_model=ClaveCatastralResponse,
    summary="Obtener clave catastral",
    responses={
        404: {"description": "Dirección no encontrada"},
        504: {"description": "Timeout del sitio CNR"},
        502: {"description": "Popup no disponible / error de parseo"},
        500: {"description": "Error interno inesperado"},
    },
)
async def obtener_clave_catastral(
    body: ClaveCatastralRequest,
) -> ClaveCatastralResponse:
    """
    Recibe una dirección y devuelve la clave catastral extraída del CNR.

    El scraping se realiza con Playwright (Chromium headless) usando un
    pool de contextos reutilizables para mejorar el rendimiento.
    """
    logger.info("Petición recibida para dirección: %s", body.direccion)
    try:
        async with pool.acquire() as context:
            resultado = await scrape_clave_catastral(context, body.direccion)
    except (DireccionNoEncontradaError, TimeoutCNRError, PopupNoDisponibleError):
        raise  # Re-lanzar para que los handlers anteriores las capturen
    except Exception as exc:
        logger.exception("Error inesperado durante el scraping: %s", exc)
        raise
    return resultado
