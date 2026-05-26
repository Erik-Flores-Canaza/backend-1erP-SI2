"""
Script de desarrollo — crear cuenta superadmin_plataforma.
Uso: python create_superadmin.py

NO usar en producción. Para producción insertar directamente en la DB.

Multi-tenant R1: el rol antiguo `superadmin` se renombró a `admin_tenant` (por-tenant).
Este script crea un `superadmin_plataforma` (cross-tenant, sin tenant_id).
Si quieres un admin de un tenant específico, usa POST /plataforma/tenants/con-admin.
"""
import sys
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.usuario import Usuario
from app.models.rol import Rol

def main() -> None:
    print("=== Crear Superadmin Plataforma (cross-tenant) ===")
    nombre   = input("Nombre completo: ").strip()
    correo   = input("Correo:          ").strip()
    password = input("Contraseña:      ").strip()

    if not nombre or not correo or not password:
        print("ERROR: Todos los campos son obligatorios.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Verificar que el rol superadmin_plataforma existe
        rol = db.query(Rol).filter(Rol.nombre == "superadmin_plataforma").first()
        if not rol:
            print("ERROR: El rol 'superadmin_plataforma' no existe. Inicia el servidor al menos una vez para que seed_roles() lo cree.")
            sys.exit(1)

        # Verificar correo único
        existente = db.query(Usuario).filter(Usuario.correo == correo).first()
        if existente:
            print(f"ERROR: Ya existe un usuario con el correo '{correo}'.")
            sys.exit(1)

        usuario = Usuario(
            rol_id          = rol.id,
            tenant_id       = None,  # superadmin_plataforma es cross-tenant
            nombre_completo = nombre,
            correo          = correo,
            hash_contrasena = hash_password(password),
            activo          = True,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)

        print(f"\n✓ Superadmin creado exitosamente.")
        print(f"  ID:     {usuario.id}")
        print(f"  Correo: {usuario.correo}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
