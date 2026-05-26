"""Helpers de multi-tenant: aplican el filtro de `tenant_id` a queries y validan acceso.

Modelo de uso (Opción C):
  - `superadmin_plataforma`: cross-tenant (sin filtro automático).
  - `admin_tenant`, `admin_taller`, `tecnico`: filtra por su `tenant_id`.
  - `cliente`: tenant_id es NULL — el router DEBE filtrar por `cliente_id`
    (este helper NO aplica filtro automático para clientes).

Patrón:
  q = db.query(Taller)
  q = aplicar_filtro_tenant(q, Taller, current_user)
  return q.all()
"""
from typing import Type, TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Query

from app.models.usuario import Usuario

T = TypeVar("T")

# Rol cross-tenant: ve todo sin restricción
ROL_CROSS_TENANT = "superadmin_plataforma"


def es_cross_tenant(user: Usuario) -> bool:
    """True si el usuario tiene rol `superadmin_plataforma` (ve todos los tenants)."""
    return bool(user.rol and user.rol.nombre == ROL_CROSS_TENANT)


def aplicar_filtro_tenant(
    query: Query[T],
    model_class: Type,
    current_user: Usuario,
) -> Query[T]:
    """Filtra una query por `tenant_id` del usuario actual.

    Casos:
      - superadmin_plataforma → sin filtro (cross-tenant).
      - usuario con tenant_id → filtra por ese tenant_id.
      - usuario sin tenant_id (p.ej. cliente global) → sin filtro automático;
        el router debe limitar por otro criterio (cliente_id, propietario_id, etc.).
    """
    if es_cross_tenant(current_user):
        return query
    if current_user.tenant_id is None:
        return query
    return query.filter(model_class.tenant_id == current_user.tenant_id)


def verificar_acceso_tenant(
    recurso_tenant_id: UUID | None,
    current_user: Usuario,
    *,
    nombre_recurso: str = "recurso",
) -> None:
    """Lanza 403 si el `current_user` intenta acceder a un recurso de otro tenant.

    Permite siempre:
      - superadmin_plataforma (cross-tenant).
      - recursos sin tenant_id (NULL — son cross-tenant por naturaleza).
      - recursos del mismo tenant del usuario.
    """
    if es_cross_tenant(current_user):
        return
    if recurso_tenant_id is None:
        return
    if current_user.tenant_id is None:
        # Usuario global (cliente) intentando acceder a recurso con tenant: forbidden
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sin acceso a {nombre_recurso} de otro tenant",
        )
    if recurso_tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sin acceso a {nombre_recurso} de otro tenant",
        )


def tenant_id_obligatorio(current_user: Usuario) -> UUID:
    """Devuelve el tenant_id del usuario o lanza 400 si no lo tiene.

    Útil cuando un operador (admin_taller, tecnico, admin_tenant) crea un recurso
    que requiere tenant_id NOT NULL.
    """
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta operación requiere un usuario con tenant asociado",
        )
    return current_user.tenant_id
