from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import SessionLocal
from app.core.seed import seed_roles
from app.routers import auth, talleres, tecnicos, usuarios, vehiculos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed inicial: inserta los 3 roles si no existen
    db = SessionLocal()
    try:
        seed_roles(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Plataforma de Emergencias Vehiculares",
    description=(
        "API REST para conectar conductores con talleres mecánicos ante emergencias vehiculares. "
        "Usa IA para clasificar incidentes y asignar talleres automáticamente.\n\n"
        "**Autenticación:** Usa `POST /auth/login` para obtener el token y luego "
        "haz clic en **Authorize** (🔒) arriba a la derecha."
    ),
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[
        {"name": "Autenticación", "description": "Login, registro, refresh y logout (CU-01, CU-02)"},
        {"name": "Usuarios", "description": "Gestión de perfil propio (CU-03)"},
        {"name": "Vehículos", "description": "CRUD de vehículos del cliente (CU-04)"},
        {"name": "Talleres", "description": "Registro de talleres y servicios (CU-10)"},
        {"name": "Técnicos", "description": "Gestión de técnicos y turnos (CU-11)"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(vehiculos.router)
app.include_router(talleres.router)
app.include_router(tecnicos.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
