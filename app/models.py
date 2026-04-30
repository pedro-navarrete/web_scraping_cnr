"""Modelos Pydantic v2 para request y response."""

from pydantic import BaseModel, Field


class ClaveCatastralRequest(BaseModel):
    """Cuerpo de la petición POST /api/clave-catastral."""

    direccion: str = Field(
        ...,
        min_length=3,
        description="Dirección a buscar en el CNR",
        examples=["COLONIA LA SULTANA, AVENIDA LAS PALMERAS, NUMERO 27"],
    )


class ClaveCatastralResponse(BaseModel):
    """Respuesta exitosa con los datos catastrales extraídos."""

    clave_catastral: str = Field(..., description="Clave catastral del inmueble")
    direccion: str = Field(..., description="Dirección completa según el CNR")
    propietario_siryc: str = Field(
        ...,
        # SIRYC: Sistema de Registro y Catastro (sistema interno del CNR)
        description="Propietario según Siryc",
    )
    propietario_poseedor: str = Field(..., description="Propietario/Poseedor/Ocupante")
