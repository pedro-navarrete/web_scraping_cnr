"""Excepciones personalizadas para la aplicación."""


class DireccionNoEncontradaError(Exception):
    """Se lanza cuando no se encuentran sugerencias para la dirección dada."""


class TimeoutCNRError(Exception):
    """Se lanza cuando el sitio del CNR no responde en el tiempo esperado."""


class PopupNoDisponibleError(Exception):
    """Se lanza cuando el popup de información catastral no aparece o no se puede parsear."""
