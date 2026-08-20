# -*- coding: utf-8 -*-
"""Alta y mantenimiento de usuarios desde la linea de comandos.

No hay pantalla de administracion porque no hay permisos: nadie es mas que
nadie dentro de la aplicacion. Las cuentas se crean aqui, en el servidor.

    python gestion_usuarios.py crear victor "Victor Cisneros"
    python gestion_usuarios.py listar
    python gestion_usuarios.py clave victor
    python gestion_usuarios.py desactivar victor

La contrasena no se pasa como argumento a proposito: se teclea al vuelo. Un
argumento queda en el historial del shell y en la lista de procesos.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from cuadre import usuarios


def _pide_clave(confirmar=True):
    clave = getpass.getpass("Contraseña: ")
    if confirmar and clave != getpass.getpass("Repítela: "):
        print("No coinciden.")
        return None
    return clave


def main():
    p = argparse.ArgumentParser(description="Usuarios del cuadre de IVA")
    sub = p.add_subparsers(dest="orden", required=True)

    c = sub.add_parser("crear", help="Da de alta un usuario")
    c.add_argument("usuario")
    c.add_argument("nombre", nargs="?", help="Nombre completo, para la interfaz")

    sub.add_parser("listar", help="Muestra los usuarios")

    k = sub.add_parser("clave", help="Cambia la contraseña y cierra sus sesiones")
    k.add_argument("usuario")

    for orden, ayuda in (("activar", "Vuelve a permitir la entrada"),
                         ("desactivar", "Impide entrar y cierra sus sesiones")):
        a = sub.add_parser(orden, help=ayuda)
        a.add_argument("usuario")

    args = p.parse_args()

    try:
        if args.orden == "crear":
            clave = _pide_clave()
            if clave is None:
                return 1
            usuarios.crea(args.usuario, args.nombre or args.usuario, clave)
            print("Creado «%s». Ya puede entrar." % args.usuario)

        elif args.orden == "listar":
            filas = usuarios.lista()
            if not filas:
                print("No hay ningún usuario. Crea el primero con:\n"
                      "  python gestion_usuarios.py crear <usuario> \"<nombre>\"")
                return 0
            print("%-18s %-28s %-8s %s" % ("USUARIO", "NOMBRE", "ESTADO", "ÚLTIMO ACCESO"))
            for u in filas:
                print("%-18s %-28s %-8s %s" % (
                    u["usuario"], u["nombre"][:28],
                    "activo" if u["activo"] else "baja",
                    u["ultimo_acceso"].strftime("%d/%m/%Y %H:%M") if u["ultimo_acceso"]
                    else "nunca"))

        elif args.orden == "clave":
            clave = _pide_clave()
            if clave is None:
                return 1
            usuarios.cambia_clave(args.usuario, clave)
            print("Cambiada. Se han cerrado las sesiones abiertas de «%s»." % args.usuario)

        else:
            activo = args.orden == "activar"
            if not usuarios.activa(args.usuario, activo):
                print("No existe el usuario «%s»." % args.usuario)
                return 1
            print("«%s» %s." % (args.usuario, "puede entrar" if activo else "ya no puede entrar"))

    except usuarios.ErrorDeUsuario as e:
        print("Error: %s" % e)
        return 1
    except Exception as e:
        print("No se ha podido hablar con la base de datos.\n  %s: %s" % (type(e).__name__, e))
        print("\n¿Está levantada?  docker compose up -d db")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
