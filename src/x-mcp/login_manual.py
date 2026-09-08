"""Script interactivo y flexible para autenticar Twitter/X en el servidor MCP.

Ofrece 2 métodos:
1. Abrir ventana de navegador para iniciar sesión interactivamente.
2. Ingresar directamente la cookie 'auth_token' copiada de tu navegador habitual.
"""

import sys
import asyncio
from browser_session import login_interactive, is_authenticated, set_auth_token, STORAGE_BACKUP

# Asegurar codificación UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    print("=" * 65)
    print("🔑 CONFIGURACIÓN DE AUTENTICACIÓN — TWITTER / X MCP")
    print("=" * 65)

    if is_authenticated():
        print(f"ℹ️ Ya existe una sesión activa guardada en:\n   {STORAGE_BACKUP}")
        resp = input("\n¿Deseas reemplazar la sesión actual? (s/N): ").strip().lower()
        if resp not in ("s", "si", "y", "yes"):
            print("Operación cancelada. Se mantiene la sesión existente.")
            return

    print("\nSelecciona cómo deseas autenticarte:")
    print("  [1] Abrir ventana de Chrome para iniciar sesión interactivamente.")
    print("  [2] Pegar la cookie 'auth_token' de tu navegador (rápido y sin login repetido).")
    
    opcion = input("\nElige una opción (1 o 2) [default: 1]: ").strip()
    if not opcion:
        opcion = "1"

    if opcion == "1":
        print("\nAbriendo navegador visible en x.com/login...")
        success = asyncio.run(login_interactive(timeout_seconds=180))
        if success:
            print("\n🎉 ¡Sesión iniciada y guardada con éxito!")
            print("Prueba la búsqueda ejecutando:")
            print("    python search_tweets.py")
        else:
            print("\n❌ No se pudo completar el inicio de sesión a tiempo.")

    elif opcion == "2":
        print("\n--- Cómo obtener la cookie auth_token en tu navegador ---")
        print("1. Ve a x.com en tu navegador habitual donde ya tienes sesión iniciada.")
        print("2. Abre Herramientas de Desarrollador (F12) -> Pestaña 'Application' o 'Almacenamiento'.")
        print("3. En el menú lateral izquierdo: 'Cookies' -> 'https://x.com'.")
        print("4. Busca la fila llamada 'auth_token' y copia su valor.")
        print("-" * 55)

        token = input("\nPega aquí el valor de 'auth_token': ").strip()
        if not token:
            print("Token vacío. Operación cancelada.")
            return
        
        ct0 = input("Pega aquí el valor de 'ct0' (opcional, presiona Enter para omitir): ").strip()
        if not ct0:
            ct0 = None

        set_auth_token(token, ct0)
        print(f"\n✅ Cookie guardada correctamente en:\n   {STORAGE_BACKUP}")
        print("\nPrueba la búsqueda ejecutando:")
        print("    python search_tweets.py")

    else:
        print("Opción inválida.")


if __name__ == "__main__":
    main()