import requests
import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Optional, Any, List


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
    """Gets token using MAC authentication and additional device parameters."""
    url = f"{base_url}/portal.php?action=handshake&type=stb&token=&JsHttpRequest=1-xml"

    headers = {"Authorization": f"MAC {mac}"}
    
    # Construir payload con parámetros opcionales
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
        return data["js"]["token"]
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        print_colored(f"Error fetching token: {e}", "red")
        if "res" in locals():
            print_colored(f"Server response: {res.text}", "yellow")
        return None

        return token

    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching token: {e}", "red")
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


def get_env_or_input(name: str, prompt: str, required: bool = True) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value

    value = input(prompt).strip()
    if required and not value:
        raise ValueError(f"El valor {name} es obligatorio.")
    return value


def build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "CatalogClient/1."
    })
    return session


def get_categories(
    session: requests.Session,
    base_url: str,
    timeout: int = 15
) -> List[Dict[str, Any]]:
    url = f"{base_url}/categories"
    res = session.get(url, timeout=timeout)
    res.raise_for_status()

    data = res.json()
    if not isinstance(data, list):
        raise ValueError("La respuesta de categorías no es una lista.")
    return data


def get_items_by_category(
    session: requests.Session,
    base_url: str,
    category_id: str,
    page: int = 1,
    timeout: int = 15
) -> List[Dict[str, Any]]:
    url = f"{base_url}/items"
    params = {
        "category_id": category_id,
        "page": page
    }

    res = session.get(url, params=params, timeout=timeout)
    res.raise_for_status()

    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("La respuesta de items no tiene formato esperado.")

    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("El campo 'items' no es una lista.")
    return items


def fetch_all_items_for_category(
    session: requests.Session,
    base_url: str,
    category: Dict[str, Any]
) -> Dict[str, Any]:
    category_id = str(category.get("id", ""))
    category_title = category.get("title", "Sin título")

    page = 1
    all_items: List[Dict[str, Any]] = []

    while True:
        items = get_items_by_category(session, base_url, category_id, page=page)
        if not items:
            break

        all_items.extend(items)
        page += 1

    return {
        "id": category_id,
        "title": category_title,
        "count": len(all_items),
        "items": all_items
    }


def save_to_json(base_name: str, payload: Any) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{base_name}_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filename


def main() -> None:
    """Main function to orchestrate the process."""
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
        
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
                "Referer": f"{base_url}/c/",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        if token:
            if get_subscription(session, base_url, token):
                headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
                vod_categories: Optional[List[Dict[str, Any]]] = get_vod_categories(session, base_url, headers)
                if vod_categories:
                    sanitized_url: str = base_url.replace("://", "_").replace("/", "_").replace(".", "_").replace(":", "_")
                    current: str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    with open(f'{sanitized_url}_{current}.m3u', 'w', encoding='utf-16') as file:
                        file.write('#EXTM3U\n')
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            futures = {executor.submit(fetch_and_save_vods, session, base_url, headers, category, file): category for category in vod_categories if category['id'] != "*"}
                            for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching categories"):
                                category: Dict[str, Any] = futures[future]
                                try:
                                    result: int = future.result()
                                    print_colored(f"Fetched {result} VODs for category: {category['title']}", "cyan")
                                except Exception as e:
                                    print_colored(f"Error fetching VODs for category {category['title']}: {e}", "red")
        results: List[Dict[str, Any]] = []

        for category in categories:
            title = category.get("title", "Sin título")
            print_msg(f"Procesando categoría: {title}")

            category_data = fetch_all_items_for_category(session, base_url, category)
            print_msg(f"  -> {category_data['count']} elementos")
            results.append(category_data)

        out = {
            "base_url": base_url,
            "total_categories": len(results),
            "categories": results
        }

        filename = save_to_json("catalogo_completo", out)
        print_msg(f"Guardado en: {filename}")

    except KeyboardInterrupt:
        print_colored("\nExiting gracefully...", "yellow")
        sys.exit(0)
    except Exception as e:
        print_colored(f"An unexpected error occurred in main: {e}", "red")


if __name__ == "__main__":
    main()
