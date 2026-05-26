"""Seed de datos de desarrollo. Solo se ejecuta si `SEED_DEV=true` en el .env.

Crea:
- 1 tenant "Auxilio Demo" (slug=auxilio-demo)
- 5 usuarios de prueba con contraseñas conocidas
- 1 taller aprobado dentro del tenant
- 1 técnico activo

Todas las operaciones son idempotentes — si los registros ya existen, se omite.
Las credenciales SOLO sirven en local; nunca debe quedar `SEED_DEV=true` en producción.
"""
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.rol import Rol
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.tenant import Tenant
from app.models.usuario import Usuario


CREDENCIALES = [
    ("super@plataforma.io", "super123", "Super Plataforma", "superadmin_plataforma", None),
    ("admin@demo.io",       "admin123", "Admin Demo",        "admin_tenant",         "auxilio-demo"),
    ("taller@demo.io",      "taller123","Dueño Taller Demo", "admin_taller",         "auxilio-demo"),
    ("tecnico@demo.io",     "tecnico123","Técnico Demo",      "tecnico",              "auxilio-demo"),
    ("cliente@demo.io",     "cliente123","Cliente Demo",      "cliente",              None),
]


def _get_or_create_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == "auxilio-demo").first()
    if tenant:
        return tenant
    tenant = Tenant(
        nombre="Auxilio Demo",
        slug="auxilio-demo",
        correo_contacto="contacto@auxilio-demo.io",
        plan="basico",
        activo=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _roles_map(db: Session) -> dict[str, Rol]:
    return {r.nombre: r for r in db.query(Rol).all()}


def _get_or_create_user(
    db: Session, correo: str, contrasena: str, nombre_completo: str,
    rol_id, tenant_id,
) -> Usuario:
    user = db.query(Usuario).filter(Usuario.correo == correo).first()
    if user:
        return user
    user = Usuario(
        correo=correo,
        hash_contrasena=hash_password(contrasena),
        nombre_completo=nombre_completo,
        rol_id=rol_id,
        tenant_id=tenant_id,
        activo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_dev(db: Session) -> None:
    tenant = _get_or_create_tenant(db)
    roles = _roles_map(db)

    creados: dict[str, Usuario] = {}
    for correo, pwd, nombre, rol_nombre, tenant_slug in CREDENCIALES:
        rol = roles.get(rol_nombre)
        if not rol:
            continue
        tid = tenant.id if tenant_slug == "auxilio-demo" else None
        creados[rol_nombre] = _get_or_create_user(db, correo, pwd, nombre, rol.id, tid)

    # Taller demo del admin_taller (si no existe)
    admin_taller = creados.get("admin_taller")
    if admin_taller:
        taller = (
            db.query(Taller)
            .filter(Taller.administrador_id == admin_taller.id)
            .first()
        )
        if not taller:
            taller = Taller(
                tenant_id=tenant.id,
                administrador_id=admin_taller.id,
                nombre="Taller Central Demo",
                direccion="Av. Demo 123",
                latitud=-17.7833,
                longitud=-63.1822,
                porcentaje_comision=10.0,
                activo=True,
                disponible=True,
                estado_aprobacion="aprobado",
            )
            db.add(taller)
            db.commit()
            db.refresh(taller)

        # Técnico demo asociado al taller
        tecnico_user = creados.get("tecnico")
        if tecnico_user:
            tecnico = (
                db.query(Tecnico)
                .filter(Tecnico.usuario_id == tecnico_user.id)
                .first()
            )
            if not tecnico:
                tecnico = Tecnico(
                    tenant_id=tenant.id,
                    usuario_id=tecnico_user.id,
                    taller_id=taller.id,
                    disponible=True,
                )
                db.add(tecnico)
                db.commit()
