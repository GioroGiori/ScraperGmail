"""Automatizacion guiada del inicio del registro de una cuenta de Google.

El script navega a Gmail mediante Playwright, abre el formulario de registro,
completa nombre, apellidos, fecha de nacimiento, genero, nombre de usuario y
contrasena, y deja el navegador abierto para continuar con las verificaciones.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import unicodedata
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


GMAIL_URL = "https://mail.google.com/"
DEFAULT_TIMEOUT_MS = 15_000


def first_visible(*locators: Locator) -> Locator | None:
    """Devuelve el primer locator visible sin depender del idioma de la pagina."""
    for locator in locators:
        try:
            candidate = locator.first
            if candidate.is_visible(timeout=1_500):
                return candidate
        except PlaywrightTimeoutError:
            continue
    return None


def click_if_visible(*locators: Locator) -> bool:
    locator = first_visible(*locators)
    if locator is None:
        return False
    locator.click()
    return True


def accept_optional_consent(page: Page) -> None:
    """Acepta el aviso de cookies solo cuando aparece."""
    click_if_visible(
        page.get_by_role("button", name=re.compile(r"^(Aceptar todo|Accept all)$", re.I)),
        page.get_by_role("button", name=re.compile(r"^(Acepto|I agree)$", re.I)),
    )


def open_signup_from_gmail(page: Page) -> Page:
    page.goto(GMAIL_URL, wait_until="domcontentloaded")
    accept_optional_consent(page)

    create_account = first_visible(
        page.get_by_role(
            "link", name=re.compile(r"Crear (una )?cuenta|Create an account", re.I)
        ),
        page.get_by_role(
            "button", name=re.compile(r"Crear (una )?cuenta|Create an account", re.I)
        ),
        page.get_by_text(
            re.compile(r"^Crear (una )?cuenta$|^Create an account$", re.I), exact=True
        ),
    )
    if create_account is None:
        raise RuntimeError(
            "No encontre el boton 'Crear una cuenta' en Gmail. "
            "Google pudo haber cambiado la pagina o ya hay una sesion iniciada."
        )
    pages_before_click = len(page.context.pages)
    create_account.click()
    page.wait_for_timeout(1_000)

    # En algunas variantes de Gmail el registro se abre en una pestana nueva.
    if len(page.context.pages) > pages_before_click:
        page = page.context.pages[-1]
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)

    # Google a veces muestra un menu para elegir el tipo de cuenta.
    click_if_visible(
        page.get_by_text(
            re.compile(r"^Para mi uso personal$|^For my personal use$|^Para mí$", re.I),
            exact=True,
        ),
        page.get_by_role(
            "menuitem", name=re.compile(r"uso personal|personal use|para mí", re.I)
        ),
    )
    page.wait_for_load_state("domcontentloaded")
    return page


def fill_name_step(
    page: Page, first_name: str, paternal_surname: str, maternal_surname: str
) -> None:
    first_name_input = first_visible(
        page.locator('input[name="firstName"]'),
        page.get_by_label(re.compile(r"Nombre|First name", re.I)),
    )
    last_name_input = first_visible(
        page.locator('input[name="lastName"]'),
        page.get_by_label(re.compile(r"Apellido|Last name", re.I)),
    )

    if first_name_input is None or last_name_input is None:
        raise RuntimeError(
            "El formulario de nombre no aparecio. Revisa la ventana del navegador; "
            "puede haber un aviso, una sesion abierta o un cambio en la pagina."
        )

    first_name_input.fill(first_name)
    last_name_input.fill(f"{paternal_surname} {maternal_surname}")

    next_button = first_visible(
        page.get_by_role("button", name=re.compile(r"^(Siguiente|Next)$", re.I)),
        page.get_by_text(re.compile(r"^(Siguiente|Next)$", re.I), exact=True),
    )
    if next_button is None:
        raise RuntimeError("No encontre el boton 'Siguiente' del formulario.")
    next_button.click()


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in value if not unicodedata.combining(character)
    ).casefold().strip()


def choose_dropdown_option(
    page: Page,
    field_names: tuple[str, ...],
    option_labels: tuple[str, ...],
    data_value: str | None = None,
) -> None:
    field_pattern = re.compile(
        rf"^({'|'.join(re.escape(name) for name in field_names)})$", re.I
    )
    native_select = first_visible(
        *(page.locator(f'select[name="{name}"]') for name in field_names),
        *(page.locator(f"select#{name}") for name in field_names),
    )

    if native_select is not None:
        if data_value is not None:
            try:
                native_select.select_option(value=data_value)
                return
            except PlaywrightError:
                pass

        normalized_expected = {normalized_text(label) for label in option_labels}
        options = native_select.locator("option")
        for index in range(options.count()):
            option = options.nth(index)
            if normalized_text(option.inner_text()) in normalized_expected:
                native_select.select_option(index=index)
                return
        raise RuntimeError("No encontré la opción solicitada en el desplegable.")

    dropdown = first_visible(
        page.get_by_role("combobox", name=field_pattern),
        page.locator("[role='combobox']").filter(has_text=field_pattern),
        page.get_by_label(field_pattern),
    )
    if dropdown is None:
        raise RuntimeError(
            f"No encontré el desplegable de {'/'.join(field_names)} en Gmail."
        )
    dropdown.click()

    option_locators = [
        page.get_by_role(
            "option", name=re.compile(rf"^{re.escape(label)}$", re.I)
        )
        for label in option_labels
    ]
    if data_value is not None:
        option_locators.insert(
            0, page.locator(f'[role="option"][data-value="{data_value}"]')
        )
    option = first_visible(*option_locators)
    if option is None:
        raise RuntimeError("No encontré la opción solicitada en el menú de Gmail.")
    option.click()


def fill_birthdate_gender_step(
    page: Page, birth_day: int, birth_month: int, birth_year: int, gender: str
) -> None:
    day_input = page.locator('input[name="day"], input#day').first
    try:
        day_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "El formulario de fecha de nacimiento no apareció después del nombre."
        ) from error

    year_input = first_visible(
        page.locator('input[name="year"]'),
        page.locator("input#year"),
        page.get_by_label(re.compile(r"Año|Year", re.I)),
    )
    if year_input is None:
        raise RuntimeError("No encontré el campo del año de nacimiento.")

    day_input.fill(str(birth_day))
    month_labels = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    choose_dropdown_option(
        page,
        ("month", "Mes", "Month"),
        (month_labels[birth_month - 1],),
        data_value=str(birth_month),
    )
    year_input.fill(str(birth_year))
    gender_labels = {
        "masculino": ("Masculino", "Male"),
        "femenino": ("Femenino", "Female"),
        "no_especificar": (
            "Prefiero no decirlo",
            "Prefiero no responder",
            "Prefiero no especificarlo",
            "Rather not say",
        ),
    }[gender]
    choose_dropdown_option(
        page, ("gender", "Género", "Genero", "Gender"), gender_labels
    )

    next_button = first_visible(
        page.get_by_role("button", name=re.compile(r"^(Siguiente|Next)$", re.I)),
        page.get_by_text(re.compile(r"^(Siguiente|Next)$", re.I), exact=True),
    )
    if next_button is None:
        raise RuntimeError(
            "No encontré el botón 'Siguiente' después de la fecha de nacimiento."
        )
    next_button.click()


def username_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).casefold()
    return "".join(character for character in ascii_value if character.isascii() and character.isalnum())


def username_candidates(
    first_name: str, paternal_surname: str, birth_year: int
) -> tuple[str, str]:
    clean_name = username_component(first_name)
    clean_surname = username_component(paternal_surname)
    if not clean_name or not clean_surname:
        raise RuntimeError(
            "No se pudo crear el nombre de usuario a partir del nombre y apellido paterno."
        )
    base = f"{clean_name}.{clean_surname}"
    return base, f"{base}.{birth_year}"


def find_username_input(page: Page) -> Locator:
    username_input = page.locator(
        'input[name="Username"], input[name="username"]'
    ).first
    try:
        if username_input.is_visible(timeout=1_000):
            return username_input
    except PlaywrightTimeoutError:
        pass

    custom_radio = page.locator(
        'input[name="usernameRadio"][value="custom"]'
    ).first
    custom_address = first_visible(
        page.locator('[data-option-jsname="UgJMid"] [data-value="custom"]'),
        page.locator('[data-option-jsname="UgJMid"]'),
        page.get_by_text(
            re.compile(
                r"^Crear tu propia direcci[oó]n de Gmail$|^Create your own Gmail address$",
                re.I,
            ),
            exact=True,
        ),
    )
    if custom_address is not None:
        custom_address.click()
        page.wait_for_timeout(300)
        if not custom_radio.is_checked():
            custom_radio.check(force=True)
        if not custom_radio.is_checked():
            raise RuntimeError(
                "No se pudo seleccionar 'Crear tu propia dirección de Gmail'."
            )
        click_next(page, "la selección del tipo de dirección de Gmail")

    try:
        username_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
        return username_input
    except PlaywrightTimeoutError:
        fallback = first_visible(
            page.get_by_label(re.compile(r"Nombre de usuario|Username", re.I)),
        )
        if fallback is None:
            raise RuntimeError("No apareció el campo para crear la dirección de Gmail.")
        return fallback


def click_next(page: Page, step_name: str) -> None:
    next_button = first_visible(
        page.get_by_role("button", name=re.compile(r"^(Siguiente|Next)$", re.I)),
        page.get_by_text(re.compile(r"^(Siguiente|Next)$", re.I), exact=True),
    )
    if next_button is None:
        raise RuntimeError(f"No encontré el botón 'Siguiente' en {step_name}.")
    next_button.click()


def username_error(page: Page) -> Locator:
    return page.get_by_text(
        re.compile(
            r"Este nombre de usuario ya est[aá] en uso(?:\. Elige otro)?|"
            r"That username is taken(?:\. Try another)?",
            re.I,
        )
    ).first


def wait_for_username_result(page: Page, username_input: Locator) -> bool:
    error_message = username_error(page)
    for _ in range(30):
        try:
            if error_message.is_visible():
                return False
        except PlaywrightError:
            pass
        try:
            if not username_input.is_visible():
                return True
        except PlaywrightError:
            return True
        page.wait_for_timeout(500)
    raise RuntimeError(
        "Google no confirmó si el nombre de usuario estaba disponible."
    )


def try_username(page: Page, username_input: Locator, candidate: str) -> bool:
    username_input.fill(candidate)
    try:
        username_error(page).wait_for(state="hidden", timeout=2_000)
    except PlaywrightTimeoutError:
        pass
    click_next(page, "el nombre de usuario")
    page.wait_for_timeout(500)
    return wait_for_username_result(page, username_input)


def capture_google_username_suggestion(page: Page) -> str | None:
    suggestion = first_visible(
        page.locator('button[data-username]'),
        page.locator('[data-username]'),
    )
    if suggestion is None:
        return None

    username = suggestion.get_attribute("data-username") or suggestion.inner_text()
    username = username.strip()
    if username.casefold().endswith("@gmail.com"):
        username = username[:-10]
    return username or None


def choose_google_username_suggestion(page: Page) -> None:
    email_pattern = re.compile(r"^[a-z0-9.]+(?:@gmail\.com)?$", re.I)
    suggestion = first_visible(
        page.locator('[role="radio"]'),
        page.locator('input[type="radio"]'),
        page.locator('[role="option"]'),
        page.locator("[data-username]"),
        page.locator('[role="button"]').filter(has_text=email_pattern),
        page.locator('[role="link"]').filter(has_text=email_pattern),
        page.get_by_text(email_pattern, exact=True),
    )
    if suggestion is None:
        raise RuntimeError(
            "Los dos nombres de usuario estaban ocupados y Google no mostró una sugerencia seleccionable."
        )
    suggestion.click()
    click_next(page, "la sugerencia de nombre de usuario")


def fill_username_step(
    page: Page, first_name: str, paternal_surname: str, birth_year: int
) -> str:
    username_input = find_username_input(page)
    base_candidate, year_candidate = username_candidates(
        first_name, paternal_surname, birth_year
    )

    if try_username(page, username_input, base_candidate):
        return base_candidate
    saved_google_suggestion = capture_google_username_suggestion(page)

    if try_username(page, username_input, year_candidate):
        return year_candidate

    if saved_google_suggestion and try_username(
        page, username_input, saved_google_suggestion
    ):
        return saved_google_suggestion

    choose_google_username_suggestion(page)
    try:
        username_input.wait_for(state="hidden", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        raise RuntimeError("Google no aceptó la sugerencia de nombre de usuario.")
    return "sugerencia de Google"


def fill_password_step(page: Page, password: str) -> None:
    password_input = page.locator('input[name="Passwd"]').first
    try:
        password_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeoutError as error:
        raise RuntimeError("No apareció el formulario para crear la contraseña.") from error

    confirmation_input = first_visible(
        page.locator('input[name="PasswdAgain"]'),
        page.get_by_label(re.compile(r"^(Confirmar|Confirm password)$", re.I)),
    )
    if confirmation_input is None:
        raise RuntimeError("No encontré el campo para confirmar la contraseña.")

    password_input.fill(password)
    confirmation_input.fill(password)
    click_next(page, "la creación de la contraseña")


def launch_context(playwright: Playwright, profile_dir: Path) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch_options = {}
    if not Path(playwright.chromium.executable_path).exists():
        # Edge ya viene instalado en Windows y usa el mismo motor Chromium.
        launch_options["channel"] = "msedge"

    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        locale="es-CL",
        viewport={"width": 1280, "height": 900},
        args=["--start-maximized"],
        **launch_options,
    )


def wait_until_browser_closes(context: BrowserContext) -> None:
    """Mantiene vivo Playwright cuando el flujo fue iniciado desde la web."""
    try:
        while context.pages:
            context.pages[0].wait_for_timeout(500)
    except PlaywrightError:
        # Cerrar la ventana termina el target y es el final esperado del flujo.
        pass


def run(
    first_name: str,
    paternal_surname: str,
    maternal_surname: str,
    birth_day: int,
    birth_month: int,
    birth_year: int,
    gender: str,
    password: str,
    profile_dir: Path,
    launched_from_web: bool = False,
) -> None:
    with sync_playwright() as playwright:
        context = launch_context(playwright, profile_dir)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)

        try:
            page = open_signup_from_gmail(page)
            fill_name_step(page, first_name, paternal_surname, maternal_surname)
            fill_birthdate_gender_step(
                page, birth_day, birth_month, birth_year, gender
            )
            selected_username = fill_username_step(
                page, first_name, paternal_surname, birth_year
            )
            fill_password_step(page, password)
            print(
                f"Registro completado hasta el usuario ({selected_username}). "
                "La contrasena fue enviada; continua con las verificaciones."
            )
            if launched_from_web:
                wait_until_browser_closes(context)
            else:
                input("Presiona Enter aqui cuando hayas terminado para cerrar el navegador...")
        except Exception:
            print(
                "La automatizacion se detuvo. La ventana queda abierta para revision.",
                file=sys.stderr,
            )
            if launched_from_web:
                wait_until_browser_closes(context)
            else:
                input("Presiona Enter para cerrar el navegador...")
            raise
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inicia de forma guiada el registro de una cuenta de Google desde Gmail."
    )
    parser.add_argument("--nombre", required=True, help="Nombre de la persona")
    parser.add_argument(
        "--apellido-paterno", required=True, help="Apellido paterno de la persona"
    )
    parser.add_argument(
        "--apellido-materno", required=True, help="Apellido materno de la persona"
    )
    parser.add_argument("--dia", required=True, type=int, help="Día de nacimiento")
    parser.add_argument("--mes", required=True, type=int, help="Mes de nacimiento")
    parser.add_argument("--anio", required=True, type=int, help="Año de nacimiento")
    parser.add_argument(
        "--genero",
        required=True,
        choices=("masculino", "femenino", "no_especificar"),
        help="Género que se seleccionará en Gmail",
    )
    parser.add_argument(
        "--perfil",
        type=Path,
        default=Path(".playwright-profile"),
        help="Carpeta local del perfil de Chromium (predeterminado: .playwright-profile)",
    )
    parser.add_argument("--desde-web", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    clean_first_name = arguments.nombre.strip()
    clean_paternal_surname = arguments.apellido_paterno.strip()
    clean_maternal_surname = arguments.apellido_materno.strip()
    if not clean_first_name or not clean_paternal_surname or not clean_maternal_surname:
        raise SystemExit("Nombre y ambos apellidos no pueden estar vacios")
    if arguments.desde_web:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Contrasena para la cuenta: ")
    if len(password) < 12:
        raise SystemExit("La contrasena debe tener al menos 12 caracteres")
    run(
        clean_first_name,
        clean_paternal_surname,
        clean_maternal_surname,
        arguments.dia,
        arguments.mes,
        arguments.anio,
        arguments.genero,
        password,
        arguments.perfil.resolve(),
        launched_from_web=arguments.desde_web,
    )
