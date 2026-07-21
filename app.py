"""Servidor local que conecta el formulario HTML con Playwright."""

from __future__ import annotations

import subprocess
import sys
import uuid
import os
import threading
import webbrowser
from datetime import date
from pathlib import Path

from flask import Flask, request, send_file


BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)


@app.get("/")
def index():
    return send_file(BASE_DIR / "index.html")


@app.post("/registrar")
def register():
    first_name = request.form.get("nombre", "").strip()
    paternal_surname = request.form.get("apellido_paterno", "").strip()
    maternal_surname = request.form.get("apellido_materno", "").strip()
    birth_day = request.form.get("dia", "").strip()
    birth_month = request.form.get("mes", "").strip()
    birth_year = request.form.get("anio", "").strip()
    genders = request.form.getlist("genero")
    password = request.form.get("contrasena", "")

    if not first_name or not paternal_surname or not maternal_surname:
        return "Nombre, apellido paterno y apellido materno son obligatorios.", 400
    if any(len(value) > 100 for value in (first_name, paternal_surname, maternal_surname)):
        return "Nombre o apellidos demasiado largos.", 400
    try:
        date(int(birth_year), int(birth_month), int(birth_day))
    except (TypeError, ValueError):
        return "La fecha de nacimiento no es válida.", 400
    allowed_genders = {"masculino", "femenino", "no_especificar"}
    if len(genders) != 1 or genders[0] not in allowed_genders:
        return "Selecciona una sola opción de género.", 400
    if len(password) < 12 or "\n" in password or "\r" in password:
        return "La contraseña generada no es válida.", 400

    profile_dir = BASE_DIR / ".playwright-profile" / uuid.uuid4().hex
    command = [
        sys.executable,
        str(BASE_DIR / "gmail_signup.py"),
        "--nombre",
        first_name,
        "--apellido-paterno",
        paternal_surname,
        "--apellido-materno",
        maternal_surname,
        "--dia",
        birth_day,
        "--mes",
        birth_month,
        "--anio",
        birth_year,
        "--genero",
        genders[0],
        "--perfil",
        str(profile_dir),
        "--desde-web",
    ]
    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdin=subprocess.PIPE,
        text=True,
    )
    if process.stdin is None:
        process.terminate()
        return "No se pudo entregar la contraseña al proceso.", 500
    process.stdin.write(password + "\n")
    process.stdin.close()

    return "Proceso iniciado. Revisa la ventana de Chromium."


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))

    if os.environ.get("OPEN_BROWSER", "0") == "1":
        url = f"http://{host}:{port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False)
