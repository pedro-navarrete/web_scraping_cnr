"""Pool de contextos de navegador Playwright para reutilización entre peticiones."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, async_playwright

from app.config import settings

logger = logging.getLogger(__name__)

# User-Agent realista para evitar bloqueos básicos por bot-detection
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BrowserPool:
    """
    Pool de contextos de Playwright.

    Mantiene una cola de BrowserContext pre-creados para reutilizarlos
    en cada petición sin necesidad de lanzar un proceso Chromium nuevo.
    """

    def __init__(self, size: int = 3) -> None:
        self._size = size
        self._browser: Browser | None = None
        self._queue: asyncio.Queue[BrowserContext] = asyncio.Queue()
        self._playwright_instance = None

    async def start(self) -> None:
        """Lanza Chromium y pre-crea los contextos del pool."""
        logger.info("Iniciando pool de navegadores (tamaño=%d) …", self._size)
        self._playwright_instance = await async_playwright().start()
        self._browser = await self._playwright_instance.chromium.launch(
            headless=settings.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        for _ in range(self._size):
            ctx = await self._create_context()
            await self._queue.put(ctx)
        logger.info("Pool listo con %d contextos.", self._size)

    async def stop(self) -> None:
        """Cierra todos los contextos y el navegador."""
        logger.info("Cerrando pool de navegadores …")
        while not self._queue.empty():
            ctx = self._queue.get_nowait()
            try:
                await ctx.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright_instance:
            await self._playwright_instance.stop()
        logger.info("Pool cerrado.")

    async def _create_context(self) -> BrowserContext:
        """Crea un nuevo contexto con User-Agent realista."""
        assert self._browser is not None, "El navegador no está iniciado."
        return await self._browser.new_context(
            user_agent=USER_AGENT,
            locale="es-SV",
            timezone_id="America/El_Salvador",
        )

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BrowserContext]:
        """
        Context manager que entrega un BrowserContext del pool.

        Si el contexto falla durante el uso, lo descarta y crea uno nuevo
        antes de devolverlo al pool.
        """
        ctx: BrowserContext = await self._queue.get()
        ok = True
        try:
            yield ctx
        except Exception:
            ok = False
            raise
        finally:
            if ok:
                # Devolver contexto sano al pool
                await self._queue.put(ctx)
            else:
                # Contexto posiblemente corrompido: cerrarlo y crear uno nuevo
                logger.warning("Contexto descartado por excepción; creando uno nuevo.")
                try:
                    await ctx.close()
                except Exception:
                    pass
                try:
                    new_ctx = await self._create_context()
                    await self._queue.put(new_ctx)
                except Exception as exc:
                    logger.error("No se pudo crear contexto de reemplazo: %s", exc)
