from sqlalchemy.orm import Session

from app.models.rol import Rol

ROLES = [
    {"nombre": "cliente", "descripcion": "Conductor que reporta emergencias vehiculares"},
    {"nombre": "admin_taller", "descripcion": "Administrador de un taller mecánico"},
    {"nombre": "tecnico", "descripcion": "Técnico que atiende emergencias en campo"},
]


def seed_roles(db: Session) -> None:
    for data in ROLES:
        existe = db.query(Rol).filter(Rol.nombre == data["nombre"]).first()
        if not existe:
            db.add(Rol(**data))
    db.commit()
