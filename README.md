# Registro guiado de Gmail con Playwright

Este proyecto abre Gmail, hace clic en **Crear una cuenta**, selecciona el uso
personal, completa nombre, apellidos, fecha de nacimiento, genero y nombre de
usuario, y pulsa **Siguiente**. El resto queda abierto para completarlo manualmente.

No intenta resolver ni eludir CAPTCHA, verificaciones por telefono u otros
controles de Google.

## Instalacion

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En Windows, el script utiliza Microsoft Edge mediante Playwright si el Chromium
propio de Playwright no esta instalado. Opcionalmente puedes instalarlo con
`python -m playwright install chromium`.

## Uso

```powershell
python gmail_signup.py --nombre "Ana" --apellido-paterno "Perez" --apellido-materno "Soto" --dia 15 --mes 7 --anio 2000 --genero femenino
```

Se abrirá Chromium y el script avanzará hasta el paso posterior al nombre. La
ventana permanecerá abierta hasta que presiones Enter en la terminal.

El perfil se guarda en `.playwright-profile` para conservar el estado del
navegador entre ejecuciones. Puedes indicar otra carpeta con `--perfil`.

## Uso desde el formulario

La forma mas directa en Windows, siguiendo el lanzador `run_local.ps1`, es:

```powershell
.\run_local.ps1
```

El script crea `.venv` si hace falta, instala las dependencias, inicia el
servidor y abre el formulario. Usa `Ctrl+C` para detenerlo. Para evitar que abra
el navegador automaticamente, ejecuta `.\run_local.ps1 -NoAbrirNavegador`.
`iniciar.ps1` se conserva como alias y ejecuta el mismo lanzador.

Si PowerShell bloquea scripts locales, puedes iniciar esta ejecucion puntual con:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_local.ps1
```

Tambien puedes iniciarlo manualmente:

Inicia el servidor local:

```powershell
python app.py
```

Luego abre `http://127.0.0.1:5000`, completa los datos y pulsa **Subir**.
El servidor iniciara Chromium y enviara nombre, ambos apellidos, fecha de
nacimiento y genero al flujo de registro. Para el correo prueba primero
`nombre.apellido`, despues `nombre.apellido.anio` y finalmente una sugerencia de
Google guardada durante el primer intento si los dos anteriores no estan
disponibles. El formulario tambien genera
una contrasena temporal y la entrega al proceso local mediante entrada estandar,
sin incluirla en los argumentos visibles del proceso. La automatizacion la
completa y confirma en Gmail; debe cambiarse despues del primer inicio de sesion.

> Google cambia periódicamente el texto y la estructura de sus páginas. Los
> selectores contemplan español e inglés, pero podrían necesitar ajustes futuros.
