"""
Servicio de IA — CU-18 y CU-19
CU-18: Transcribe audio (Whisper) + analiza imágenes (GPT-4o Vision)
CU-19: Clasifica, asigna prioridad y genera resumen estructurado (GPT-4o)

Si OPENAI_API_KEY no está configurada, devuelve valores seguros que no bloquean el flujo.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.evidencia import Evidencia
from app.models.incidente import Incidente

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")

CLASIFICACIONES_VALIDAS = {"bateria", "llanta", "choque", "motor", "electrico", "otro", "incierto"}
PRIORIDADES_VALIDAS     = {"baja", "media", "alta", "incierto"}

_STUB_RESULT = {
    "clasificacion": "otro",
    "confianza": 0.8,
    "resumen": "IA no configurada — revisión manual requerida",
}

_PROMPT_SISTEMA = """\
Eres un sistema experto en clasificación de emergencias vehiculares.
Analiza la información proporcionada y responde ÚNICAMENTE con un JSON válido:

{
  "clasificacion": "<bateria|llanta|choque|motor|electrico|otro|incierto>",
  "prioridad":     "<baja|media|alta|incierto>",
  "confianza":     <float 0.0-1.0>,
  "resumen":       "<1-2 oraciones concisas describiendo el problema>"
}

Reglas de clasificación:
- bateria  : problema de arranque, batería descargada, luces tenues
- llanta   : llanta pinchada, desinflada o reventada
- choque   : colisión, accidente, golpe con vehículo u objeto
- motor    : falla mecánica, ruidos anómalos, humo, sobrecalentamiento
- electrico: falla eléctrica (alarma, cortocircuito, luces) que no sea batería
- otro     : emergencia vehicular que no encaja en las anteriores
- incierto : información insuficiente para clasificar con certeza

Reglas de prioridad:
- alta   : riesgo inmediato (choque, motor humeando, persona atrapada)
- media  : vehículo completamente inmovilizado sin riesgo inmediato
- baja   : el vehículo puede funcionar parcialmente
- incierto: no hay suficiente información

Devuelve confianza < 0.5 si la información es ambigua o muy escasa.
Responde SOLO el JSON, sin texto adicional."""


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _ia_disponible() -> bool:
    key = settings.OPENAI_API_KEY
    return bool(key) and key != "tu_api_key"


def _get_client():
    from openai import OpenAI
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _mime_de_extension(ext: str) -> str:
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")


def _transcribir_audio(client, ruta: Path) -> str:
    """Transcribe audio con Whisper-1."""
    with open(ruta, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="es",
        )
    return result.text


def transcribir(ruta: Path) -> str | None:
    """Transcribe un archivo de audio a texto (Whisper). None si IA no disponible."""
    if not _ia_disponible():
        return None
    try:
        return _transcribir_audio(_get_client(), ruta)
    except Exception as exc:  # noqa: BLE001
        logger.error("Transcripción de voz falló: %s", exc)
        return None


# Prompt para CU-46: interpretar una petición de reporte hablada → filtros JSON
_PROMPT_REPORTE_VOZ = """\
Eres un asistente que interpreta peticiones habladas de reportes de servicios de
auxilio vehicular. El usuario es un cliente que pide un reporte de SUS servicios.
Hoy es {hoy}. A partir del texto, responde ÚNICAMENTE con un JSON válido:

{{
  "desde":   "<YYYY-MM-DD o null>",
  "hasta":   "<YYYY-MM-DD o null>",
  "estado":  "<finalizado|cancelado|null>",
  "formato": "<pdf|excel|html>"
}}

Reglas:
- Interpreta rangos relativos respecto de hoy ("este mes", "la semana pasada",
  "los últimos 3 meses", "este año"). Si no menciona fechas, deja ambas en null.
- "estado" solo si el usuario lo menciona explícitamente (servicios finalizados,
  cancelados); si no, null.
- "formato" por defecto "pdf"; usa "excel" si dice Excel/hoja de cálculo y "html"
  si dice HTML/página web.
- Responde SOLO el JSON, sin texto adicional."""


def interpretar_peticion_reporte(texto: str) -> dict:
    """CU-46 — Convierte la transcripción en filtros estructurados de reporte.

    Devuelve dict con claves desde/hasta/estado/formato. Ante cualquier fallo
    devuelve valores seguros (sin filtros, PDF).
    """
    seguro = {"desde": None, "hasta": None, "estado": None, "formato": "pdf"}
    if not _ia_disponible() or not texto.strip():
        return seguro
    try:
        from datetime import date as _date
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _PROMPT_REPORTE_VOZ.format(hoy=_date.today().isoformat())},
                {"role": "user", "content": texto},
            ],
            response_format={"type": "json_object"},
            max_tokens=120,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content or "{}")
        fmt = data.get("formato", "pdf")
        if fmt not in ("pdf", "excel", "html"):
            fmt = "pdf"
        estado = data.get("estado")
        if estado not in ("finalizado", "cancelado"):
            estado = None
        return {
            "desde": data.get("desde") or None,
            "hasta": data.get("hasta") or None,
            "estado": estado,
            "formato": fmt,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Interpretación de petición de reporte falló: %s", exc)
        return seguro


def _analizar_imagen(client, ruta: Path) -> str:
    """Analiza imagen de daño vehicular con GPT-4o Vision."""
    with open(ruta, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    ext = ruta.suffix.lower().lstrip(".")
    mime = _mime_de_extension(ext)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Eres un experto en mecánica automotriz. "
                        "Analiza esta imagen de una emergencia vehicular. "
                        "Describe en 2-3 oraciones qué daño o falla identificas. "
                        "Si no puedes determinarlo, indícalo."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ],
        }],
        max_tokens=300,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# CU-18: Procesar evidencias multimodales
# ---------------------------------------------------------------------------

def process_evidencias(incidente_id: UUID, db: Session) -> dict:
    """
    Carga todas las evidencias del incidente, procesa imágenes (GPT-4o Vision)
    y audios (Whisper), guarda los resultados en la BD y retorna el contexto
    acumulado para que CU-19 lo use.
    """
    if not _ia_disponible():
        return _STUB_RESULT

    client = _get_client()

    incidente: Incidente | None = (
        db.query(Incidente).filter(Incidente.id == incidente_id).first()
    )
    evidencias: list[Evidencia] = (
        db.query(Evidencia).filter(Evidencia.incidente_id == incidente_id).all()
    )

    imagenes_analizadas: list[str] = []
    transcripciones: list[str] = []

    for ev in evidencias:
        if not ev.url_archivo:
            continue

        # url_archivo llega como "/uploads/nombre.ext" — resolver ruta local
        nombre = ev.url_archivo.replace("/uploads/", "").lstrip("/")
        ruta = UPLOAD_DIR / nombre

        if not ruta.exists():
            logger.warning("CU-18 — archivo no encontrado: %s", ruta)
            continue

        try:
            if ev.tipo == "imagen":
                analisis = _analizar_imagen(client, ruta)
                ev.analisis_ia = analisis
                imagenes_analizadas.append(analisis)
                logger.info("CU-18 — imagen analizada: %s", ev.id)

            elif ev.tipo == "audio":
                transcripcion = _transcribir_audio(client, ruta)
                ev.transcripcion = transcripcion
                transcripciones.append(transcripcion)
                logger.info("CU-18 — audio transcrito: %s", ev.id)

        except Exception as exc:
            logger.error("CU-18 — error procesando evidencia %s: %s", ev.id, exc)

    db.flush()

    return {
        "descripcion_texto": (incidente.descripcion_texto or "") if incidente else "",
        "transcripciones": transcripciones,
        "imagenes_analizadas": imagenes_analizadas,
    }


# ---------------------------------------------------------------------------
# CU-19: Generar resumen estructurado
# ---------------------------------------------------------------------------

def generate_resumen(incidente_id: UUID, resultado_ia: dict, db: Session) -> dict:
    """
    Con el contexto de CU-18, llama a GPT-4o para obtener clasificación,
    prioridad, confianza y resumen estructurado.
    """
    if not _ia_disponible():
        return {
            "prioridad":       "media",
            "clasificacion_ia": "otro",
            "confianza_ia":    0.8,
            "resumen_ia":      "IA no configurada — clasificación manual requerida",
        }

    # Si el resultado viene del stub (sin evidencias procesadas)
    if "clasificacion" in resultado_ia and "confianza" in resultado_ia:
        return {
            "prioridad":        "media" if resultado_ia["confianza"] >= 0.5 else "incierto",
            "clasificacion_ia": resultado_ia["clasificacion"],
            "confianza_ia":     resultado_ia["confianza"],
            "resumen_ia":       resultado_ia.get("resumen", ""),
        }

    # Construir el contexto textual para el LLM
    partes: list[str] = []
    if resultado_ia.get("descripcion_texto"):
        partes.append(f"Descripción del cliente: {resultado_ia['descripcion_texto']}")
    for t in resultado_ia.get("transcripciones", []):
        partes.append(f"Audio transcrito: {t}")
    for a in resultado_ia.get("imagenes_analizadas", []):
        partes.append(f"Análisis visual: {a}")

    if not partes:
        return {
            "prioridad":        "incierto",
            "clasificacion_ia": "incierto",
            "confianza_ia":     0.0,
            "resumen_ia":       "Sin evidencias suficientes para clasificar.",
        }

    contexto = "\n".join(partes)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user",   "content": contexto},
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.1,
        )

        data: dict = json.loads(response.choices[0].message.content or "{}")

        clasificacion = data.get("clasificacion", "otro")
        if clasificacion not in CLASIFICACIONES_VALIDAS:
            clasificacion = "otro"

        prioridad = data.get("prioridad", "media")
        if prioridad not in PRIORIDADES_VALIDAS:
            prioridad = "media"

        confianza = float(data.get("confianza", 0.5))
        confianza = max(0.0, min(1.0, confianza))

        logger.info(
            "CU-19 — clasificación=%s prioridad=%s confianza=%.2f",
            clasificacion, prioridad, confianza,
        )

        return {
            "prioridad":        prioridad,
            "clasificacion_ia": clasificacion,
            "confianza_ia":     confianza,
            "resumen_ia":       data.get("resumen", ""),
        }

    except Exception as exc:
        logger.error("CU-19 — error al generar resumen: %s", exc)
        return {
            "prioridad":        "media",
            "clasificacion_ia": "otro",
            "confianza_ia":     0.5,
            "resumen_ia":       "Error al generar resumen IA — revisión manual.",
        }
