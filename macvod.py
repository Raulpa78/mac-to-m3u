import requests
import requests
import json
import os
from datetime import datetime
from urllib.parse import urlparse
import sys
import base64
import re
from typing import Dict, Tuple, Optional, Any, List

def print_colored(text: str, color: str) -> None:
    """Prints colored text."""
    colors: Dict[str, str] = {
        "green": "\033[92m",
        "red": "\033[91m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "magenta": "\033[95m",
    }
    color_code: str = colors.get(color.lower(), "\033[0m")
    print(f"{color_code}{text}\033[0m")


def input_colored(prompt: str, color: str) -> str:
    """Gets user input with a colored prompt."""
    colors: Dict[str, str] = {
        "green": "\033[92m",
        "red": "\033[91m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "magenta": "\033[95m",
    }
    color_code: str = colors.get(color.lower(), "\033[0m")
    return input(f"{color_code}{prompt}\033[0m")

def get_base_url() -> str:
    """Gets base URL from environment variable or user input."""
    base_url_input = os.getenv('IPTV_URL')  # ðŸ'ˆ Lee del secret
    if not base_url_input:
        base_url_input = input_colored("Enter IPTV link: ", "cyan")
    
    parsed_url = urlparse(base_url_input)
    scheme = parsed_url.scheme or "http"
    host = parsed_url.hostname
    port = parsed_url.port or 80
    return f"{scheme}://{host}:{port}"

def get_mac_address() -> str:
    """Gets MAC address from environment variable or user input."""
    mac = os.getenv('MAC_ADDRESS')  # ðŸ'ˆ Lee del secret
    if mac:
        return mac.upper()
    
    return input_colored("Input Mac address: ", "cyan").upper()

def get_serial_number() -> str:
    """Gets serial number from environment variable or user input."""
    serial = os.getenv('SERIAL_NUMBER')
    if serial:
        return serial
    
    return input_colored("Input serial number (optional, press Enter to skip): ", "cyan")


def get_device_id() -> str:
    """Gets device ID from environment variable or user input."""
    device_id = os.getenv('DEVICE_ID')
    if device_id:
        return device_id
    
    return input_colored("Input device ID (optional, press Enter to skip): ", "cyan")


def get_device_id_2() -> str:
    """Gets secondary device ID from environment variable or user input."""
    device_id_2 = os.getenv('DEVICE_ID_2')
    if device_id_2:
        return device_id_2
    
    return input_colored("Input secondary device ID (optional, press Enter to skip): ", "cyan")
    

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

def get_subscription(
    session: requests.Session, base_url: str, token: str, timeout: int = 10
) -> bool:
    """Gets subscription information using a Bearer token."""
    url = f"{base_url}/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"

    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = session.get(url, headers=headers, timeout=timeout)
        res.raise_for_status()
        data = res.json()
        mac = data["js"]["mac"]
        
        # Mostrar información adicional si está disponible
        serial = data.get("js", {}).get("serial", "N/A")
        device_id = data.get("js", {}).get("device_id", "N/A")
        device_id_2 = data.get("js", {}).get("device_id_2", "N/A")
        expiry = data.get("js", {}).get("phone", "N/A")
        
        print_colored(f"MAC = {mac}\nSerial = {serial}\nDevice ID = {device_id}\nDevice ID 2 = {device_id_2}\nExpiry = {expiry}", "green")
        return True
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        print_colored(f"Error fetching subscription info: {e}", "red")
        if "res" in locals():
            print_colored(f"Server response: {res.text}", "yellow")
        return False

def get_vod_categories(session: requests.Session, base_url: str, headers: Dict[str, str], timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    Get the list of VOD categories from the server.

    Args:
        session (requests.Session): The current session.
        base_url (str): The base URL.
        headers (Dict[str, str]): The request headers.
        timeout (int): The request timeout in seconds.

    Returns:
        Optional[List[Dict[str, Any]]]: The list of VOD categories or None if the request fails.
    """
    url: str = f"{base_url}/portal.php?type=vod&action=get_categories&JsHttpRequest=1-xml"
    try:
        res: requests.Response = session.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        if res.status_code == 200:
            return json.loads(res.text)["js"]
        else:
            print_colored("Failed to fetch VOD categories", "red")
            return None
    except requests.RequestException as e:
        print_colored(f"Error fetching VOD categories: {e}", "red")
        return None

def get_vod_list(session: requests.Session, base_url: str, headers: Dict[str, str], category_id: str, page: int = 1, timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    Get the list of VOD items for a specific category.

    Args:
        session (requests.Session): The current session.
        base_url (str): The base URL.
        headers (Dict[str, str]): The request headers.
        category_id (str): The category ID.
        page (int): The page number for pagination.
        timeout (int): The request timeout in seconds.

    Returns:
        Optional[List[Dict[str, Any]]]: The list of VOD items or None if the request fails.
    """
    url: str = (f"{base_url}/portal.php?type=vod&action=get_ordered_list&movie_id=0&season_id=0&episode_id=0&row=0&"
                f"JsHttpRequest=1-xml&category={category_id}&sortby=added&fav=0&hd=0&not_ended=0&abc=*&genre=*&years=*&search=&p={page}")
    try:
        res: requests.Response = session.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        if res.status_code == 200:
            return json.loads(res.text)["js"]["data"]
        else:
            print_colored("Failed to fetch VOD list", "red")
            return None
    except requests.RequestException as e:
        print_colored(f"Error fetching VOD list: {e}", "red")
        return None

def decode_cmd(cmd: str) -> Dict[str, Any]:
    """
    Decode a base64-encoded command.

    Args:
        cmd (str): The base64-encoded command.

    Returns:
        Dict[str, Any]: The decoded command as a dictionary.
    """
    decoded_bytes: bytes = base64.b64decode(cmd)
    decoded_str: str = decoded_bytes.decode('utf-8')
    return json.loads(decoded_str)

def fetch_play_link(session: requests.Session, base_url: str, cmd: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch the play link for a VOD item.

    Args:
        session (requests.Session): The current session.
        base_url (str): The base URL.
        cmd (str): The command to fetch the play link.
        timeout (int): The request timeout in seconds.

    Returns:
        Optional[str]: The play link or None if the request fails.
    """
    url: str = f"{base_url}/portal.php?type=vod&action=create_link&cmd={quote(cmd)}"
    try:
        res: requests.Response = session.get(url, timeout=timeout, allow_redirects=False)
        if res.status_code == 200:
            data: Dict[str, Any] = json.loads(res.text)
            play_token: str = data['js']['cmd'].split(' ')[1]
            return play_token
        else:
            print_colored("Failed to fetch play link", "red")
            return None
    except requests.RequestException as e:
        print_colored(f"Error fetching play link: {e}", "red")
        return None

def save_vod_list(file, vod_data: List[Dict[str, Any]], session: requests.Session, base_url: str, category_title: str) -> int:
    """
    Save the list of VOD items to a file.

    Args:
        file: The file object to write to.
        vod_data (List[Dict[str, Any]]): The list of VOD items.
        session (requests.Session): The current session.
        base_url (str): The base URL.
        category_title (str): The title of the category.

    Returns:
        int: The number of VOD items saved.
    """
    count: int = 0
    for vod in vod_data:
        name: str = vod['name']
        logo: str = vod.get('screenshot_uri', '')
        cmd: str = vod['cmd']
        play_link: Optional[str] = fetch_play_link(session, base_url, cmd)
        if play_link:
            vod_str: str = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{category_title}",{name}\n{play_link}\n'
            count += 1
            file.write(vod_str)
    return count

def fetch_and_save_vods(session: requests.Session, base_url: str, headers: Dict[str, str], category: Dict[str, Any], file) -> int:
    """
    Fetch and save VOD items for a specific category.

    Args:
        session (requests.Session): The current session.
        base_url (str): The base URL.
        headers (Dict[str, str]): The request headers.
        category (Dict[str, Any]): The category information.
        file: The file object to write to.

    Returns:
        int: The total number of VOD items saved.
    """
    category_id: str = category['id']
    category_title: str = category['title']
    if category_id == "*":
        return 0

    page: int = 1
    total_count: int = 0
    while True:
        vod_data: Optional[List[Dict[str, Any]]] = get_vod_list(session, base_url, headers, category_id, page)
        if not vod_data:
            break
        count: int = save_vod_list(file, vod_data, session, base_url, category_title)
        total_count += count
        page += 1
    return total_count

def main() -> None:
    """
    Main function to handle the IPTV VOD fetching and saving process.

    Returns:
        None
    """
    try:
        base_url: str = get_base_url()
        mac: str = get_mac_address()
        session: requests.Session = requests.Session()
        session.cookies.update({'mac': f'{mac}'})
        token: Optional[str] = get_token(session, base_url, mac)
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
    except KeyboardInterrupt:
        print_colored("\nExiting gracefully...", "yellow")
        sys.exit(0)
    except Exception as e:
        print_colored(f"Unexpected error: {e}", "red")
        sys.exit(1)

if __name__ == "__main__":
    main()
