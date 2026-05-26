from sqlalchemy.orm import Session

from app.models.rol import Rol

# 5 roles del sistema multi-tenant:
# - cliente: conductor global (cross-tenant)
# - admin_taller: gestiona UN taller dentro de un tenant
# - tecnico: ejecuta servicios en campo
# - admin_tenant: administra una red de talleres (UN tenant) — reemplaza al antiguo 'superadmin'
# - superadmin_plataforma: cross-tenant, gestiona tenants (CU-28)
ROLES = [
    {"nombre": "cliente", "descripcion": "Conductor que reporta emergencias vehiculares (cross-tenant)"},
    {"nombre": "admin_taller", "descripcion": "Administrador de un taller mecánico dentro de un tenant"},
    {"nombre": "tecnico", "descripcion": "Técnico que atiende emergencias en campo"},
    {"nombre": "admin_tenant", "descripcion": "Administrador de una red de talleres (un tenant)"},
    {"nombre": "superadmin_plataforma", "descripcion": "Administrador global de la plataforma (cross-tenant)"},
]


def seed_roles(db: Session) -> None:
    for data in ROLES:
        existe = db.query(Rol).filter(Rol.nombre == data["nombre"]).first()
        if not existe:
            db.add(Rol(**data))
    db.commit()
