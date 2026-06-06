"""Rutas de reportes — CU-44 (admin_tenant), CU-45 (cliente), CU-46 (voz cliente).

Un solo motor (`report_service`) emite los 3 formatos (PDF / Excel / HTML).
El alcance depende del rol: el cliente solo ve sus servicios; el admin_tenant ve
su red (con aislamiento multi-tenant heredado de `kpi_service`).

Endpoints:
  GET  /reportes/cliente?formato=&desde=&hasta=&estado=&incluir_resumen=&incluir_detalle=
  POST /reportes/cliente/voz         (multipart audio)  — CU-46
  GET  /reportes/admin?formato=&desde=&hasta=&secciones=
"""
import uuid as _uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin_tenant, require_cliente
from app.models.usuario import Usuario
from app.services import ia_service, report_service

router = APIRouter(prefix="/reportes", tags=["Reportes"])

UPLOAD_DIR = Path("uploads")


def _adjuntar(contenido: bytes, media_type: str, filename: str) -> Response:
    """Devuelve el archivo como descarga (Content-Disposition: attachment)."""
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ════════════════════════════════════════════════════════════════════════════
# CU-45 — Reporte de servicios del cliente
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/cliente",
    summary="CU-45 — Reporte de mis servicios (PDF / Excel / HTML)",
)
def reporte_cliente(
    formato: str = "pdf",
    desde: date | None = None,
    hasta: date | None = None,
    estado: str | None = None,
    incluir_resumen: bool = True,
    incluir_detalle: bool = True,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    doc = report_service.datos_reporte_cliente(
        db, cliente,
        desde=desde, hasta=hasta, estado=estado,
        incluir_resumen=incluir_resumen, incluir_detalle=incluir_detalle,
    )
    contenido, media, filename = report_service.generar(doc, formato, "mis-servicios")
    return _adjuntar(contenido, media, filename)


@router.post(
    "/cliente/voz",
    summary="CU-46 — Interpretar una petición de reporte hablada (Whisper + GPT-4o)",
)
async def reporte_cliente_voz(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    """Recibe el audio del cliente, lo transcribe y extrae los filtros del reporte.

    Devuelve la transcripción + los filtros interpretados para que la app los
    muestre ("Entendí: …") y dispare la descarga vía GET /reportes/cliente.
    """
    extension = Path(audio.filename or "audio.m4a").suffix or ".m4a"
    ruta = UPLOAD_DIR / f"voz-{_uuid.uuid4()}{extension}"
    ruta.write_bytes(await audio.read())
    try:
        transcripcion = ia_service.transcribir(ruta) or ""
        filtros = ia_service.interpretar_peticion_reporte(transcripcion)
    finally:
        try:
            ruta.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    return {
        "transcripcion": transcripcion,
        "desde": filtros["desde"],
        "hasta": filtros["hasta"],
        "estado": filtros["estado"],
        "formato": filtros["formato"],
    }


# ════════════════════════════════════════════════════════════════════════════
# CU-44 — Reporte operacional del tenant (admin_tenant)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/admin",
    summary="CU-44 — Reporte operacional del tenant (PDF / Excel / HTML)",
)
def reporte_admin(
    formato: str = "pdf",
    desde: date | None = None,
    hasta: date | None = None,
    secciones: str | None = None,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tenant),
):
    """`secciones`: lista separada por comas de
    {resumen,por_tipo,talleres,zonas,sla,satisfaccion}. Vacío = todas."""
    sel = (
        {s.strip() for s in secciones.split(",") if s.strip()}
        if secciones else None
    )
    doc = report_service.datos_reporte_admin(
        db, admin, desde=desde, hasta=hasta, secciones_sel=sel,
    )
    contenido, media, filename = report_service.generar(doc, formato, "reporte-operacional")
    return _adjuntar(contenido, media, filename)
