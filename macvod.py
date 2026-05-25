import requests
import json
import os
from datetime import datetime
from urllib.parse import urlparse
import sys
from typing import Dict, Tuple, Optional, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed


def print_colored(text: str, color: str) -> None:
    colors: Dict[str, str] = {
        "green": "\033[92m",
        "red": "\033[91m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "magenta": "\033[95m",
    }
    color_code: str = colors.get(color.lower(), "\033[m")
    print(f"{color_code}{text}\033[m")


def input_colored(prompt: str, color: str) -> str:
    colors: Dict[str, str] = {
        "green": "\033[92m",
        "red": "\033[91m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "magenta": "\033[95m",
    }
    color_code: str = colors.get(color.lower(), "\033[m")
    return input(f"{color_code}{prompt}\033[m")


def get_base_url() -> str:
    base_url_input = os.getenv("IPTV_URL", "").strip()
    if not base_url_input:
        if not sys.stdin.isatty():
            raise ValueError("Falta IPTV_URL y no hay entrada interactiva disponible.")
        base_url_input = input_colored("Enter IPTV link: ", "cyan").strip()

    parsed_url = urlparse(base_url_input)
    if not parsed_url.scheme or not parsed_url.hostname:
        raise ValueError("La URL introducida no es válida. Ejemplo: http://dominio:puerto")

    scheme = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port

    if port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def get_mac_address() -> str:
    mac = os.getenv("MAC_ADDRESS", "").strip()
    if mac:
        return mac.upper()

    if not sys.stdin.isatty():
        raise ValueError("Falta MAC_ADDRESS y no hay entrada interactiva disponible.")

    try:
        return input_colored("Input Mac address: ", "cyan").strip().upper()
    except EOFError:
        raise ValueError("No se pudo leer la MAC desde entrada estándar.")


def get_serial_number() -> str:
    serial = os.getenv("SERIAL_NUMBER", "").strip()
    if serial:
        return serial

    if not sys.stdin.isatty():
        return ""

    try:
        return input_colored("Input serial number (optional, press Enter to skip): ", "cyan").strip()
    except EOFError:
        return ""


def get_device_id() -> str:
    device_id = os.getenv("DEVICE_ID", "").strip()
    if device_id:
        return device_id

    if not sys.stdin.isatty():
        return ""

    try:
        return input_colored("Input device ID (optional, press Enter to skip): ", "cyan").strip()
    except EOFError:
        return ""


def get_device_id_2() -> str:
    device_id_2 = os.getenv("DEVICE_ID_2", "").strip()
    if device_id_2:
        return device_id_2

    if not sys.stdin.isatty():
        return ""

    try:
        return input_colored("Input secondary device ID (optional, press Enter to skip): ", "cyan").strip()
    except EOFError:
        return ""


def get_token(
    session: requests.Session, 
    base_url: str, 
    mac: str, 
    serial_number: str = "",
    device_id: str = "",
    device_id_2: str = "",
    timeout: int = 10
) -> Optional[str]:
    """Obtiene token usando autenticación MAC."""
    url = f"{base_url}/portal.php?action=handshake&type=stb&token=&JsHttpRequest=1-xml"
    headers = {"Authorization": f"MAC {mac}"}

    payload = {}
    if serial_number:
        payload["serial"] = serial_number
    if device_id:
        payload["device_id"] = device_id
    if device_id_2:
        payload["device_id_2"] = device_id_2

    try:
        if payload:
            res = session.post(url, headers=headers, json=payload, timeout=timeout)
        else:
            res = session.get(url, headers=headers, timeout=timeout)

        res.raise_for_status()
        data = res.json()

        token = data.get("js", {}).get("token")
        if not token:
            print_colored("No se encontró token en la respuesta.", "red")
            print_colored(res.text, "yellow")
            return None

        return token

    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching token: {e}", "red")
        if "res" in locals():
            print_colored(f"Server response: {res.text}", "yellow")
        return None

def get_subscription(
    session: requests.Session,
    base_url: str,
    token: str,
    timeout: int = 10
) -> bool:
    url = f"{base_url}/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = session.get(url, headers=headers, timeout=timeout)
        res.raise_for_status()
        data = res.json()

        js = data.get("js", {})
        mac = js.get("mac", "N/A")
        serial = js.get("serial", "N/A")
        device_id = js.get("device_id", "N/A")
        device_id_2 = js.get("device_id_2", "N/A")
        expiry = js.get("phone", "N/A")

        print_colored(
            f"MAC = {mac}\nSerial = {serial}\nDevice ID = {device_id}\nDevice ID 2 = {device_id_2}\nExpiry = {expiry}",
            "green"
        )
        return True

    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching subscription info: {e}", "red")
        return False



def get_vod_categories(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    timeout: int = 10
) -> Optional[List[Dict[str, Any]]]:
    """
    Obtiene la lista de categorías VOD del servidor.
    """
    url = f"{base_url}/portal.php?type=vod&action=get_categories&JsHttpRequest=1-xml"

    try:
        res = session.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        res.raise_for_status()

        data = res.json()
        categories = data.get("js")

        if not isinstance(categories, list):
            print_colored("La respuesta no contiene una lista válida de categorías.", "red")
            print_colored(res.text, "yellow")
            return None

        return categories

    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching VOD categories: {e}", "red")
        return None


def fetch_and_save_vods(session, base_url, headers, category, file) -> int:
    category_id = category['id']
    category_title = category['title']

    if category_id == "*":
        return 

    page = 1
     

    while True:
        vod_data = get_vod_list(session, base_url, headers, category_id, page)
        if not vod_data:
            break

        count = save_vod_list(file, vod_data, session, base_url, category_title)
        total_count += count
        page += 1

    return total_count

def save_to_json(base_name: str, payload: Any) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{base_name}_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filename


def main() -> None:
    try:
        base_url = get_base_url()
        mac = get_mac_address()
        serial_number = get_serial_number()
        device_id = get_device_id()
        device_id_2 = get_device_id_2()

        session = requests.Session()
        session.cookies.update({"mac": mac})

        if serial_number:
            session.cookies.update({"serial": serial_number})
        if device_id:
            session.cookies.update({"device_id": device_id})
        if device_id_2:
            session.cookies.update({"device_id_2": device_id_2})

        session.headers.update({
            "User-Agent": "Mozilla/5.",
            "Referer": f"{base_url}/c/",
            "Accept": "application/json, text/javascript, */*; q=.01",
            "X-Requested-With": "XMLHttpRequest",
        })

        token = get_token(session, base_url, mac, serial_number, device_id, device_id_2)
        if not token:
            print_colored("No se pudo obtener el token.", "red")
            sys.exit(1)

        print_colored(f"Token obtenido: {token}", "green")

        headers = {"Authorization": f"Bearer {token}"}
        vod_categories = get_vod_categories(session, base_url, headers)

        if not vod_categories:
            print_colored("No se pudieron obtener categorías VOD.", "red")
            sys.exit(1)

        results: List[Dict[str, Any]] = []

        for category in vod_categories:
            category_id = category.get("id")
            category_title = category.get("title", "Sin título")

            print_colored(f"Procesando categoría: {category_title}", "cyan")

            results.append({
                "id": category_id,
                "title": category_title
            })

        print_colored(f"Total categorías procesadas: {len(results)}", "green")

    except KeyboardInterrupt:
        print_colored("\nExiting gracefully...", "yellow")
        sys.exit()
    except Exception as e:
        print_colored(f"An unexpected error occurred in main: {e}", "red")
        sys.exit(1)


if __name__ == "__main__":
    main()
