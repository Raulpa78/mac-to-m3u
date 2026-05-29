import requests
import json
import os
import re
import time
import sys
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Optional, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed


# ---------------------- COLORED OUTPUT ----------------------

def print_colored(text: str, color: str) -> None:
    colors = {
        "green": "\033[92m", "red": "\033[91m", "blue": "\033[94m",
        "yellow": "\033[93m", "cyan": "\033[96m", "magenta": "\033[95m",
    }
    print(f"{colors.get(color.lower(), '')}{text}\033[0m")


def input_colored(prompt: str, color: str) -> str:
    colors = {
        "green": "\033[92m", "red": "\033[91m", "blue": "\033[94m",
        "yellow": "\033[93m", "cyan": "\033[96m", "magenta": "\033[95m",
    }
    return input(f"{colors.get(color.lower(), '')}{prompt}\033[0m")


# ---------------------- ENV / INPUT HELPERS ----------------------

def _get_env_or_input(env_var: str, prompt: str, required: bool = True) -> str:
    value = os.getenv(env_var, "").strip()
    if value:
        return value
    if not sys.stdin.isatty():
        if required:
            raise ValueError(f"Falta {env_var} y no hay entrada interactiva disponible.")
        return ""
    try:
        return input_colored(prompt, "cyan").strip()
    except EOFError:
        if required:
            raise ValueError(f"No se pudo leer {env_var}.")
        return ""


def get_base_url() -> str:
    base_url_input = _get_env_or_input("IPTV_URL", "Enter IPTV link: ")
    parsed = urlparse(base_url_input)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("URL inválida. Ejemplo: http://dominio:puerto")
    if parsed.port:
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    return f"{parsed.scheme}://{parsed.hostname}"


def get_mac_address() -> str:
    return _get_env_or_input("MAC_ADDRESS", "Input MAC address: ").upper()


def get_serial_number() -> str:
    return _get_env_or_input("SERIAL_NUMBER", "Input serial number (optional): ", required=False)


def get_device_id() -> str:
    return _get_env_or_input("DEVICE_ID", "Input device ID (optional): ", required=False)


def get_device_id_2() -> str:
    return _get_env_or_input("DEVICE_ID_2", "Input secondary device ID (optional): ", required=False)


# ---------------------- AUTH ----------------------

def get_token(
    session: requests.Session, base_url: str, mac: str,
    serial_number: str = "", device_id: str = "", device_id_2: str = "",
    timeout: int = 15
) -> Optional[str]:
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
        token = res.json().get("js", {}).get("token")
        if not token:
            print_colored("No se encontró token en la respuesta.", "red")
            return None
        return token
    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching token: {e}", "red")
        return None


# ---------------------- VOD ----------------------

def get_vod_categories(
    session: requests.Session, base_url: str, headers: Dict[str, str], timeout: int = 15
) -> Optional[List[Dict[str, Any]]]:
    url = f"{base_url}/portal.php?type=vod&action=get_categories&JsHttpRequest=1-xml"
    try:
        res = session.get(url, headers=headers, timeout=timeout)
        res.raise_for_status()
        categories = res.json().get("js")
        if not isinstance(categories, list):
            print_colored("Respuesta inválida de categorías.", "red")
            return None
        return categories
    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching VOD categories: {e}", "red")
        return None


def get_vod_page(
    session: requests.Session, base_url: str, headers: Dict[str, str],
    category_id: str, page: int = 1, timeout: int = 15
) -> Optional[Dict[str, Any]]:
    url = (
        f"{base_url}/portal.php?type=vod&action=get_ordered_list"
        f"&category={category_id}&p={page}&JsHttpRequest=1-xml"
    )
    try:
        res = session.get(url, headers=headers, timeout=timeout)
        res.raise_for_status()
        return res.json().get("js", {})
    except (requests.RequestException, json.JSONDecodeError) as e:
        print_colored(f"Error fetching VOD page {page} of category {category_id}: {e}", "red")
        return None


def get_vod_stream_link(
    session: requests.Session, base_url: str, headers: Dict[str, str],
    cmd: str, timeout: int = 15
) -> Optional[str]:
    """Resuelve el cmd a una URL real de stream."""
    url = (
        f"{base_url}/portal.php?type=vod&action=create_link"
        f"&cmd={cmd}&JsHttpRequest=1-xml"
    )
    try:
        res = session.get(url, headers=headers, timeout=timeout)
        res.raise_for_status()
        data = res.json().get("js", {})
        link = data.get("cmd", "")
        # El link suele venir como "ffmpeg http://..." o sólo la URL
        match = re.search(r"(https?://\S+)", link)
        if match:
            return match.group(1)
        return link or None
    except (requests.RequestException, json.JSONDecodeError):
        return None


def fetch_category_vods(
    session: requests.Session, base_url: str, headers: Dict[str, str],
    category: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Descarga todos los VODs de una categoría (paginado)."""
    category_id = str(category.get("id", ""))
    category_title = category.get("title", "Sin título")

    if category_id in ("*", ""):
        return []

    vods: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = get_vod_page(session, base_url, headers, category_id, page)
        if not data:
            break
        items = data.get("data", [])
        if not items:
            break
        for item in items:
            item["_category_title"] = category_title
            vods.append(item)

        total_items = int(data.get("total_items", 0))
        max_page_items = int(data.get("max_page_items", 14) or 14)
        if page * max_page_items >= total_items:
            break
        page += 1

    print_colored(f"  [{category_title}] -> {len(vods)} VODs", "blue")
    return vods


def resolve_link_with_retry(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    cmd: str,
    content_type: str = "vod",
    max_retries: int = 3,
    timeout: int = 15,
) -> Optional[str]:
    """
    Resuelve un cmd llamando a create_link.
    Funciona tanto para VOD como para Live (itv).
    """
    if not cmd:
        return None

    # Endpoint correcto según tipo
    action = "create_link"
    url = (
        f"{base_url}/portal.php?type={content_type}&action={action}"
        f"&cmd={requests.utils.quote(cmd, safe='')}"
        f"&JsHttpRequest=1-xml"
    )

    for attempt in range(1, max_retries + 1):
        try:
            res = session.get(url, headers=headers, timeout=timeout)
            res.raise_for_status()
            data = res.json().get("js", {})
            link = data.get("cmd", "") or ""

            # Limpiar posibles prefijos: "ffmpeg ", "ffrt ", "auto ", número inicial, etc.
            link = link.strip()
            link = re.sub(r"^(ffmpeg|ffrt|auto)\s+", "", link, flags=re.IGNORECASE)
            link = re.sub(r"^\d+\s+", "", link)  # a veces empieza con "1 http://..."

            # Extraer URL final
            match = re.search(r"(https?://\S+)", link)
            if match:
                return match.group(1)

            return None  # respondió pero sin URL útil

        except (requests.RequestException, json.JSONDecodeError) as e:
            if attempt < max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))
            else:
                print_colored(f"  ✗ Falló tras {max_retries} intentos: {e}", "red")
    return None


# ---------------------- FILTERING ----------------------

def filter_categories(
    categories: List[Dict[str, Any]],
    patterns: List[str],
    mode: str = "startswith",
    case_sensitive: bool = False,
) -> List[Dict[str, Any]]:
    """
    Filtra categorías cuyo título coincida con alguno de los patrones.
    - mode="startswith": el título empieza por el patrón
    - mode="contains":   el patrón aparece en cualquier parte del título
    """
    if not patterns:
        return categories

    norm_patterns = [p.strip() for p in patterns if p.strip()]
    if not case_sensitive:
        norm_patterns = [p.lower() for p in norm_patterns]

    filtered: List[Dict[str, Any]] = []
    discarded: List[str] = []

    for cat in categories:
        title = str(cat.get("title", ""))
        haystack = title if case_sensitive else title.lower()

        if mode == "startswith":
            match = any(haystack.startswith(p) for p in norm_patterns)
        else:  # contains
            match = any(p in haystack for p in norm_patterns)

        if match:
            filtered.append(cat)
        else:
            discarded.append(title)

    print_colored(
        f"Filtro aplicado (modo={mode}, patrones={norm_patterns}): "
        f"{len(filtered)} incluidas / {len(discarded)} descartadas",
        "cyan",
    )

    if filtered:
        print_colored("Categorías incluidas:", "green")
        for cat in filtered:
            print_colored(f"  ✓ {cat.get('title')}", "green")

    return filtered


# ---------------------- M3U ----------------------

def sanitize(text: str) -> str:
    if not text:
        return ""
    return str(text).replace(",", " ").replace("\n", " ").strip()


def build_m3u(vods: List[Dict[str, Any]], resolve_links: bool = False,
              session: Optional[requests.Session] = None,
              base_url: str = "", headers: Optional[Dict[str, str]] = None) -> str:
    """
    Construye un archivo M3U agrupado por categoría.
    Si resolve_links=True, hace una petición extra por cada VOD para obtener la URL real
    (más lento pero el M3U funciona directamente).
    """
    lines = ["#EXTM3U"]
    for vod in vods:
        name = sanitize(vod.get("name", "Sin nombre"))
        logo = vod.get("screenshot_uri") or vod.get("cover") or ""
        group = sanitize(vod.get("_category_title", "VOD"))
        cmd = vod.get("cmd", "")

        if resolve_links and session and headers:
            stream_url = get_vod_stream_link(session, base_url, headers, cmd)
        else:
            # Link "portal-style": muchos reproductores Stalker-compatibles lo aceptan
            match = re.search(r"(https?://\S+)", cmd)
            stream_url = match.group(1) if match else cmd

        if not stream_url:
            continue

        lines.append(
            f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{name}'
        )
        lines.append(stream_url)
    return "\n".join(lines) + "\n"


# ---------------------- OUTPUT ----------------------

def save_file(filename: str, content: str) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print_colored(f"Archivo guardado: {filename}", "green")


def save_json(filename: str, payload: Any) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print_colored(f"JSON guardado: {filename}", "green")


# ---------------------- MAIN ----------------------

def main() -> None:
    try:
        base_url = get_base_url()
        mac = get_mac_address()
        serial_number = get_serial_number()
        device_id = get_device_id()
        device_id_2 = get_device_id_2()

        resolve_links = os.getenv("RESOLVE_LINKS", "false").lower() == "true"
        max_workers = int(os.getenv("MAX_WORKERS", "5"))

        session = requests.Session()
        session.cookies.update({"mac": mac})
        if serial_number:
            session.cookies.update({"serial": serial_number})
        if device_id:
            session.cookies.update({"device_id": device_id})
        if device_id_2:
            session.cookies.update({"device_id_2": device_id_2})

        session.headers.update({
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "Referer": f"{base_url}/c/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        })

        # 1) Token
        token = get_token(session, base_url, mac, serial_number, device_id, device_id_2)
        if not token:
            print_colored("No se pudo obtener el token.", "red")
            sys.exit(1)
        print_colored(f"Token obtenido: {token}", "green")

        headers = {"Authorization": f"Bearer {token}"}

        # 2) Categorías VOD
        vod_categories = get_vod_categories(session, base_url, headers)
        if not vod_categories:
            print_colored("No se pudieron obtener categorías VOD.", "red")
            sys.exit(1)
        print_colored(f"Categorías VOD encontradas: {len(vod_categories)}", "cyan")

        # 2.1) FILTRAR categorías
        filter_raw = os.getenv("CATEGORY_FILTERS", "").strip()
        if filter_raw:
            filter_mode = os.getenv("CATEGORY_FILTER_MODE", "startswith").strip().lower()
            filter_case_sensitive = os.getenv("CATEGORY_FILTER_CASE_SENSITIVE", "false").lower() == "true"

            patterns = [p.strip() for p in filter_raw.split(",") if p.strip()]
            if patterns:
                vod_categories = filter_categories(
                    vod_categories,
                    patterns=patterns,
                    mode=filter_mode,
                    case_sensitive=filter_case_sensitive,
                )

            if not vod_categories:
                print_colored("Ninguna categoría coincide con el filtro.", "yellow")
                sys.exit(0)

        # 3) Descargar VODs (en paralelo por categoría)
        all_vods: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_cat = {
                executor.submit(fetch_category_vods, session, base_url, headers, cat): cat
                for cat in vod_categories
            }
            for future in as_completed(future_to_cat):
                cat = future_to_cat[future]
                try:
                    vods = future.result()
                    all_vods.extend(vods)
                except Exception as e:
                    print_colored(f"Error en categoría {cat.get('title')}: {e}", "red")

        print_colored(f"Total VODs descargados: {len(all_vods)}", "green")

        if not all_vods:
            print_colored("No se encontraron VODs.", "yellow")
            sys.exit(0)

        # 4) Carpeta de salida: utilizar el directorio actual
        output_dir = os.getcwd()  # Cambiado para usar el directorio actual
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # 5) Guardar
        JSON (backup completo) json_path = os.path.join(output_dir, f"vods_{timestamp}.json") 
        save_json(json_path, all_vods) 
        # También una copia "latest" para que el workflow siempre tenga ruta fija 
        save_json(os.path.join(output_dir, "vods_latest.json"), all_vods)

       # 6) Construir M3U global agrupado por categoría
        print_colored("Construyendo M3U...", "cyan")
        m3u_content = build_m3u(
        all_vods,
        resolve_links=resolve_links,
        session=session,
        base_url=base_url,
        headers=headers,
    )
    m3u_path = os.path.join(output_dir, f"vods_{timestamp}.m3u")
    save_file(m3u_path, m3u_content)
    save_file(os.path.join(output_dir, "vods_latest.m3u"), m3u_content)

    # 7) M3U separados por grupo (un archivo por categoría)
    per_group_dir = os.path.join(output_dir, "groups")
    os.makedirs(per_group_dir, exist_ok=True)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for vod in all_vods:
        g = vod.get("_category_title", "VOD")
        grouped.setdefault(g, []).append(vod)

    for group_name, items in grouped.items():
        safe_name = re.sub(r"[^\w\-]+", "_", group_name).strip("_") or "grupo"
        group_m3u = build_m3u(
            items,
            resolve_links=resolve_links,
            session=session,
            base_url=base_url,
            headers=headers,
        )
        save_file(os.path.join(per_group_dir, f"{safe_name}.m3u"), group_m3u)

    print_colored("✓ Proceso completado correctamente.", "green")

except KeyboardInterrupt:
    print_colored("\nExiting gracefully...", "yellow")
    sys.exit(0)
except Exception as e:
    print_colored(f"An unexpected error occurred in main: {e}", "red")
    sys.exit(1)
 

if name == "main":
   main()
