"""
Router de evidencias — parte de CU-05 (Reportar emergencia).
Permite subir archivos (imagen, audio, texto) asociados a un incidente.
Los archivos se guardan en el directorio local `uploads/` y se sirven como estáticos.
"""
import os
import uuid as _uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_cliente
from app.models.evidencia import Evidencia
from app.models.incidente import Incidente
from app.models.usuario import Usuario
from app.schemas.evidencia import EvidenciaResponse

router = APIRouter(prefix="/incidentes", tags=["Evidencias"])

# Directorio donde se guardan los archivos subidos
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

TIPOS_VALIDOS = {"imagen", "audio", "texto"}
EXTENSIONES_PERMITIDAS = {
    "imagen": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "audio":  {".mp3", ".wav", ".ogg", ".m4a", ".aac"},
    "texto":  {".txt", ".pdf"},
}


@router.post(
    "/{incidente_id}/evidencias",
    response_model=EvidenciaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subir_evidencia(
    incidente_id: UUID,
    tipo: str = Form(..., description="Tipo de evidencia: 'imagen', 'audio' o 'texto'"),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-05 — Sube un archivo de evidencia (imagen, audio o texto) para un incidente.
    El archivo se guarda localmente y la URL se registra en la tabla EVIDENCIAS.
    """
    # Validar tipo
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo inválido. Valores permitidos: {sorted(TIPOS_VALIDOS)}",
        )

    # Validar que el incidente existe y pertenece al cliente
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado o no pertenece al usuario autenticado",
        )

    # Validar extensión del archivo
    _, extension = os.path.splitext(archivo.filename or "")
    extension = extension.lower()
    permitidas = EXTENSIONES_PERMITIDAS[tipo]
    if extension not in permitidas:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extensión no permitida para tipo '{tipo}'. Permitidas: {sorted(permitidas)}",
        )

    # Guardar archivo con nombre único
    nombre_archivo = f"{_uuid.uuid4()}{extension}"
    ruta_archivo = UPLOAD_DIR / nombre_archivo
    contenido = await archivo.read()
    ruta_archivo.write_bytes(contenido)

    url_archivo = f"/uploads/{nombre_archivo}"

    evidencia = Evidencia(
        incidente_id=incidente_id,
        tipo=tipo,
        url_archivo=url_archivo,
    )
    db.add(evidencia)
    db.commit()
    db.refresh(evidencia)
    return evidencia


@router.get("/{incidente_id}/evidencias", response_model=list[EvidenciaResponse])
def listar_evidencias(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """Lista todas las evidencias de un incidente del cliente autenticado."""
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    return db.query(Evidencia).filter(Evidencia.incidente_id == incidente_id).all()
