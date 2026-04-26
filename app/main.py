from contextlib import asynccontextmanager
from pathlib import Path

import stripe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.seed import seed_roles
from app.routers import (
    asignaciones,
    auth,
    evidencias,
    incidentes,
    notificaciones,
    talleres,
    tecnicos,
    usuarios,
    vehiculos,
)
from app.routers.admin import admin_router, public_router as solicitudes_public_router
from app.routers.mensajes import http_router as mensajes_http_router
from app.routers.mensajes import ws_router as mensajes_ws_router
from app.routers.pagos import router as pagos_router
from app.routers.ws_notificaciones import router as ws_notif_router
from app.services.fcm_service import init_firebase
import app.models.taller_favorito  # noqa: F401 — registra la tabla en SQLAlchemy

# Inicializar Stripe con la clave secreta
stripe.api_key = settings.STRIPE_SECRET_KEY

# Crear directorio de uploads si no existe
Path("uploads").mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Guardar el event loop para que los endpoints síncronos puedan emitir por WS
    import asyncio
    from app.services import notificacion_service
    notificacion_service._main_loop = asyncio.get_running_loop()

    # Seed inicial: inserta los 3 roles si no existen
    db = SessionLocal()
    try:
        seed_roles(db)
    finally:
        db.close()
    # Inicializar Firebase (no-op si no está configurado)
    init_firebase()
    yield


app = FastAPI(
    title="Plataforma de Emergencias Vehiculares",
    description=(
        "API REST para conectar conductores con talleres mecánicos ante emergencias vehiculares. "
        "Usa IA para clasificar incidentes y asignar talleres automáticamente.\n\n"
        "**Autenticación:** Usa `POST /auth/login` para obtener el token y luego "
        "haz clic en **Authorize** (🔒) arriba a la derecha."
    ),
    version="3.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[
        {"name": "Autenticación",   "description": "Login, registro, refresh y logout (CU-01, CU-02)"},
        {"name": "Usuarios",        "description": "Gestión de perfil propio (CU-03)"},
        {"name": "Vehículos",       "description": "CRUD de vehículos del cliente (CU-04)"},
        {"name": "Talleres",        "description": "Registro de talleres, servicios, historial y métricas (CU-10, CU-15, CU-26, CU-27)"},
        {"name": "Técnicos",        "description": "Gestión de técnicos, turnos y ubicación (CU-11, CU-16)"},
        {"name": "Incidentes",      "description": "Reportar y monitorear emergencias (CU-05, CU-06, CU-14)"},
        {"name": "Evidencias",      "description": "Subida de archivos de evidencia — imagen, audio, texto (CU-05)"},
        {"name": "Asignaciones",    "description": "Gestión de solicitudes, técnicos y completado (CU-12, CU-13, CU-17)"},
        {"name": "Pagos",           "description": "Pago del servicio con Stripe (CU-07)"},
        {"name": "Mensajes",        "description": "Historial de chat cliente-taller (CU-08)"},
        {"name": "Chat WebSocket",  "description": "Chat en tiempo real vía WebSocket (CU-08)"},
        {"name": "Notificaciones",  "description": "Notificaciones automáticas y gestión manual (CU-21, CU-09)"},
        {"name": "Superadmin — Solicitudes (público)", "description": "Formulario público de solicitud de registro de taller (CU-22)"},
        {"name": "Superadmin — Panel", "description": "Panel de administración global — solo rol superadmin (CU-23, CU-24, CU-25)"},
        {"name": "Health",          "description": "Verificación de estado del servidor"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos subidos (evidencias)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Ciclo 1 ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(vehiculos.router)
app.include_router(talleres.router)
app.include_router(tecnicos.router)

# ── Ciclo 2 ──────────────────────────────────────────────────────────────────
app.include_router(incidentes.router)
app.include_router(evidencias.router)
app.include_router(asignaciones.router)
app.include_router(notificaciones.router)

# ── Ciclo 3 ──────────────────────────────────────────────────────────────────
app.include_router(pagos_router)
app.include_router(mensajes_http_router)
app.include_router(mensajes_ws_router, prefix="/ws")
app.include_router(ws_notif_router, prefix="/ws")

# ── Ciclo 3+ — Superadmin & Multi-sucursal ───────────────────────────────────
app.include_router(solicitudes_public_router)   # POST /solicitudes-taller (CU-22)
app.include_router(admin_router)                # /admin/* (CU-23, CU-24, CU-25)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "version": "3.0.0"}
