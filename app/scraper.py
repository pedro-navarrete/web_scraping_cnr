"""
Lógica de web scraping contra el portal CNR de El Salvador.

IMPORTANTE: Los selectores CSS/XPath definidos como constantes al inicio
de este archivo pueden cambiar si el sitio actualiza su frontend (ArcGIS/Esri).
Actualizar estas constantes si el scraping deja de funcionar.
"""

import logging
from typing import Any

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

from app.config import settings
from app.exceptions import (
    DireccionNoEncontradaError,
    PopupNoDisponibleError,
    TimeoutCNRError,
)
from app.models import ClaveCatastralResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTES DE SELECTORES
# Ajustar si el sitio cambia su estructura HTML/CSS.
# ---------------------------------------------------------------------------

# Botón/flecha que despliega el panel de búsqueda en el header
SELECTOR_DROPDOWN_TOGGLE = (
    "div.esri-search__container button,"  # botón de búsqueda ArcGIS estándar
    " .esri-search__submit-button,"
    " button[aria-label*='earch'],"
    " button[title*='earch'],"
    " .header-search-toggle,"       # clases genéricas del header CNR
    " .search-toggle,"
    " [class*='search'][class*='toggle'],"
    " [class*='expand'][class*='button'],"
    " .esri-expand__button,"        # widget Expand de ArcGIS (flecha ▼ / ▲)
    " button.esri-widget--button"
)

# Input donde se escribe la dirección
SELECTOR_INPUT_BUSQUEDA = (
    "input.esri-search__input,"
    " input[placeholder*='irec'],"        # "dirección"
    " input[placeholder*='ugar'],"        # "lugar"
    " input[type='text'][class*='search']"
)

# Lista de sugerencias (contenedor)
SELECTOR_SUGERENCIAS_LISTA = (
    ".esri-search__suggestions-list,"
    " ul[class*='suggest'],"
    " [role='listbox'],"
    " ul[class*='search-result']"
)

# Primer ítem de la lista de sugerencias
SELECTOR_PRIMERA_SUGERENCIA = (
    ".esri-search__suggestions-list li:first-child,"
    " ul[class*='suggest'] li:first-child,"
    " [role='listbox'] [role='option']:first-child,"
    " ul[class*='search-result'] li:first-child"
)

# Icono lupa (fallback si no aparecen sugerencias)
SELECTOR_LUPA = (
    "button.esri-search__submit-button,"
    " button[aria-label*='earch'],"
    " button[title*='Buscar'],"
    " button[class*='search'][class*='submit']"
)

# Popup/panel de Información Catastral
SELECTOR_POPUP_TITULO = (
    ".esri-popup__header-title,"
    " .esri-feature__title,"
    " [class*='popup'][class*='title'],"
    " .popup-title"
)

# Contenido del popup (tabla o lista con los datos)
SELECTOR_POPUP_CONTENIDO = (
    ".esri-popup__content,"
    " .esri-feature__content,"
    " [class*='popup'][class*='content'],"
    " .esri-feature-fields__field-data"
)

# Tiempo de espera para el popup (ms) — puede ser más lento que el page timeout
POPUP_WAIT_MS = 20_000

# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


async def scrape_clave_catastral(
    context: BrowserContext,
    direccion: str,
) -> ClaveCatastralResponse:
    """
    Realiza el scraping del portal CNR y devuelve los datos catastrales.

    Parámetros:
        context: BrowserContext del pool de Playwright.
        direccion: Dirección a buscar.

    Retorna:
        ClaveCatastralResponse con los datos extraídos.

    Lanza:
        DireccionNoEncontradaError: si no hay sugerencias.
        TimeoutCNRError: si el sitio no carga a tiempo.
        PopupNoDisponibleError: si el popup no aparece o no se puede parsear.
    """
    page: Page = await context.new_page()
    try:
        return await _do_scrape(page, direccion)
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _do_scrape(page: Page, direccion: str) -> ClaveCatastralResponse:
    """Lógica interna de scraping dentro de una página ya abierta."""

    timeout = settings.page_timeout_ms

    # ------------------------------------------------------------------
    # 1. Navegar al portal del CNR
    # ------------------------------------------------------------------
    logger.info("Navegando a %s …", settings.cnr_url)
    try:
        await page.goto(
            settings.cnr_url,
            wait_until="domcontentloaded",
            timeout=timeout,
        )
    except PlaywrightTimeout as exc:
        raise TimeoutCNRError(f"Timeout al cargar el portal CNR: {exc}") from exc

    # Esperar a que la UI de ArcGIS esté lista (widget de búsqueda visible)
    logger.info("Esperando widget de búsqueda …")
    try:
        await page.wait_for_selector(
            SELECTOR_INPUT_BUSQUEDA + ", " + SELECTOR_DROPDOWN_TOGGLE,
            state="attached",
            timeout=timeout,
        )
    except PlaywrightTimeout as exc:
        raise TimeoutCNRError(
            f"El widget de búsqueda no apareció en {timeout} ms: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 2. Intentar hacer visible el input: primero probamos si ya está
    #    visible; si no, hacemos click en el botón de expansión/toggle.
    # ------------------------------------------------------------------
    input_locator = page.locator(SELECTOR_INPUT_BUSQUEDA).first
    input_visible = await input_locator.is_visible()

    if not input_visible:
        logger.info("Input no visible, haciendo click en el dropdown/toggle …")
        toggle = page.locator(SELECTOR_DROPDOWN_TOGGLE).first
        try:
            await toggle.click(timeout=timeout)
            await page.wait_for_selector(
                SELECTOR_INPUT_BUSQUEDA,
                state="visible",
                timeout=timeout,
            )
        except PlaywrightTimeout as exc:
            raise TimeoutCNRError(
                f"El input de búsqueda no se hizo visible después del click: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # 3. Escribir la dirección en el input
    # ------------------------------------------------------------------
    logger.info("Escribiendo dirección: %s", direccion)
    try:
        await input_locator.fill(direccion, timeout=timeout)
    except PlaywrightTimeout as exc:
        raise TimeoutCNRError(f"No se pudo escribir en el input: {exc}") from exc

    # ------------------------------------------------------------------
    # 4. Esperar sugerencias; si no aparecen, hacer click en la lupa
    # ------------------------------------------------------------------
    logger.info("Esperando sugerencias …")
    sugerencias_aparecieron = False
    try:
        await page.wait_for_selector(
            SELECTOR_SUGERENCIAS_LISTA,
            state="visible",
            timeout=5_000,  # timeout corto para este paso
        )
        sugerencias_aparecieron = True
    except PlaywrightTimeout:
        logger.warning("No aparecieron sugerencias; usando lupa como fallback.")

    if sugerencias_aparecieron:
        # ------------------------------------------------------------------
        # 5a. Seleccionar la primera sugerencia
        # ------------------------------------------------------------------
        logger.info("Seleccionando primera sugerencia …")
        primera = page.locator(SELECTOR_PRIMERA_SUGERENCIA).first
        try:
            await primera.click(timeout=timeout)
        except PlaywrightTimeout as exc:
            raise DireccionNoEncontradaError(
                f"No se pudo hacer click en la primera sugerencia: {exc}"
            ) from exc
    else:
        # ------------------------------------------------------------------
        # 5b. Fallback: click en la lupa
        # ------------------------------------------------------------------
        logger.info("Haciendo click en la lupa (fallback) …")
        lupa = page.locator(SELECTOR_LUPA).first
        try:
            await lupa.click(timeout=timeout)
        except PlaywrightTimeout as exc:
            raise DireccionNoEncontradaError(
                f"No se encontraron sugerencias y la lupa tampoco respondió: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # 6. Esperar el popup de Información Catastral
    # ------------------------------------------------------------------
    logger.info("Esperando popup de Información Catastral …")
    try:
        await page.wait_for_selector(
            SELECTOR_POPUP_TITULO,
            state="visible",
            timeout=POPUP_WAIT_MS,
        )
    except PlaywrightTimeout as exc:
        raise PopupNoDisponibleError(
            f"El popup de Información Catastral no apareció: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 7. Extraer datos del popup
    # ------------------------------------------------------------------
    logger.info("Extrayendo datos del popup …")
    datos = await _extraer_datos_popup(page)
    logger.info("Datos extraídos: %s", datos)
    return ClaveCatastralResponse(**datos)


async def _extraer_datos_popup(page: Page) -> dict[str, Any]:
    """
    Extrae los campos del popup de Información Catastral.

    El popup de ArcGIS muestra los datos como una tabla de campo/valor.
    Intentamos leer el contenido de texto completo y parsearlo.
    """
    # Esperar a que el contenido del popup esté disponible
    contenido_locator = page.locator(SELECTOR_POPUP_CONTENIDO).first
    try:
        await contenido_locator.wait_for(state="visible", timeout=POPUP_WAIT_MS)
    except PlaywrightTimeout as exc:
        raise PopupNoDisponibleError(
            f"El contenido del popup no está disponible: {exc}"
        ) from exc

    # Extraer el texto HTML del popup para parsearlo
    contenido_html: str = await contenido_locator.inner_html(timeout=10_000)
    contenido_texto: str = await contenido_locator.inner_text(timeout=10_000)

    # Intentar parsear usando el DOM estructurado de ArcGIS (tabla field/value)
    datos = await _parsear_popup_arcgis(page, contenido_html, contenido_texto)
    return datos


async def _parsear_popup_arcgis(
    page: Page,
    html: str,  # noqa: ARG001 – Se guarda para debug futuro
    texto: str,
) -> dict[str, Any]:
    """
    Parsea los datos del popup de ArcGIS.

    ArcGIS presenta los campos en una estructura como:
      <div class="esri-feature-fields__field-header">Clave Catastral</div>
      <div class="esri-feature-fields__field-data">0501U26-190</div>

    Como fallback, también intentamos leer con JavaScript directamente
    de las celdas de la tabla visible.
    """

    # --- Intento 1: selectores de campo/valor de ArcGIS ---
    campo_val: dict[str, str] = {}
    try:
        campo_val = await page.evaluate(
            """() => {
                const result = {};
                // ArcGIS JSAPI popup fields
                const headers = document.querySelectorAll(
                    '.esri-feature-fields__field-header, '
                    + '[class*="field"][class*="header"], '
                    + 'th, .field-name, .attr-name'
                );
                const values = document.querySelectorAll(
                    '.esri-feature-fields__field-data, '
                    + '[class*="field"][class*="data"], '
                    + 'td, .field-value, .attr-value'
                );
                for (let i = 0; i < headers.length; i++) {
                    const key = (headers[i].innerText || '').trim();
                    const val = values[i] ? (values[i].innerText || '').trim() : '';
                    if (key) result[key] = val;
                }
                return result;
            }"""
        )
    except Exception as exc:
        logger.warning("Error al evaluar JS para extraer campos: %s", exc)

    # --- Normalizar claves al formato esperado ---
    clave_catastral = _buscar_campo(
        campo_val,
        texto,
        ["clave catastral", "clave_catastral", "catastral"],
    )
    direccion = _buscar_campo(
        campo_val,
        texto,
        ["dirección", "direccion", "address", "direcci"],
    )
    propietario_siryc = _buscar_campo(
        campo_val,
        texto,
        ["propietario según siryc", "propietario siryc", "siryc", "propietario_siryc"],
    )
    propietario_poseedor = _buscar_campo(
        campo_val,
        texto,
        [
            "propietario/poseedor/ocupante",
            "propietario poseedor",
            "poseedor",
            "ocupante",
        ],
    )

    # Si no obtuvimos la clave catastral, el popup no es parseable
    if not clave_catastral:
        raise PopupNoDisponibleError(
            "No se encontró la clave catastral en el popup. "
            f"Campos detectados: {list(campo_val.keys())}"
        )

    return {
        "clave_catastral": clave_catastral,
        "direccion": direccion or "NO DISPONIBLE",
        "propietario_siryc": propietario_siryc or "NO DISPONIBLE",
        "propietario_poseedor": propietario_poseedor or "NO DISPONIBLE",
    }


def _buscar_campo(
    campo_val: dict[str, str],
    texto_completo: str,
    claves_posibles: list[str],
) -> str:
    """
    Busca un campo en el diccionario campo_val (insensible a mayúsculas).
    Si no lo encuentra, intenta extraerlo del texto completo del popup.
    """
    lower_map = {k.lower(): v for k, v in campo_val.items()}

    for clave in claves_posibles:
        clave_lower = clave.lower()
        # Búsqueda exacta
        if clave_lower in lower_map:
            return lower_map[clave_lower]
        # Búsqueda parcial
        for k, v in lower_map.items():
            if clave_lower in k:
                return v

    # Fallback: buscar en texto libre (línea siguiente a la etiqueta)
    lineas = [l.strip() for l in texto_completo.splitlines() if l.strip()]
    for i, linea in enumerate(lineas):
        for clave in claves_posibles:
            if clave.lower() in linea.lower() and i + 1 < len(lineas):
                return lineas[i + 1]

    return ""
