"""
Cargador de configuración YAML para hosts
"""
import os
import importlib
from pathlib import Path
from typing import Dict, Any, Type
import yaml

# Mapeo de nombres de resolver a módulos
# Formato: "NombreResolver": "nombre_modulo"
RESOLVER_MODULE_MAP = {
    "RanozResolver": "ranoz",
    "PassThroughResolver": "passtrought",
    "AnonFileResolver": "anonfile",
    "GofileResolver": "gofile",
    "UploadFlixResolver": "uploadflix",
    "OneFichierResolver": "onefichier",
    "FiledotResolver": "filedot",
    "DesiUploadResolver": "desiupload",
    "PixelDrainResolver": "pixeldrain",
    "AxfcResolver": "axfc",
    "FileMirageResolver": "filemirage",
    "UploadHiveResolver": "uploadhive",
    "UploadeeResolver": "uploadee",
    "SendNowResolver": "sendnow",
    "KrakenFilesResolver": "krakenfiles",
    "UsersDriveResolver": "usersdrive",
    "ExloadResolver": "exload",
}

# Cache para almacenar las clases ya cargadas
_RESOLVER_CACHE: Dict[str, Type] = {}


def _get_resolver_class(resolver_name: str) -> Type:
    """
    Obtiene la clase del resolver de forma dinámica.
    
    Args:
        resolver_name: Nombre del resolver (ej: "RanozResolver")
    
    Returns:
        Clase del resolver
    """
    # Verificar si ya está en cache
    if resolver_name in _RESOLVER_CACHE:
        return _RESOLVER_CACHE[resolver_name]
    
    # Obtener el nombre del módulo
    if resolver_name not in RESOLVER_MODULE_MAP:
        raise ValueError(
            f"Resolver desconocido: {resolver_name}. "
            f"Resolvers disponibles: {list(RESOLVER_MODULE_MAP.keys())}"
        )
    
    module_name = RESOLVER_MODULE_MAP[resolver_name]
    
    # Importar el módulo dinámicamente
    try:
        module = importlib.import_module(f"fetchr.hosts.{module_name}")
        resolver_class = getattr(module, resolver_name)
        
        # Guardar en cache
        _RESOLVER_CACHE[resolver_name] = resolver_class
        return resolver_class
    except ImportError as e:
        raise ImportError(
            f"No se pudo importar el módulo 'fetchr.hosts.{module_name}' para el resolver '{resolver_name}': {e}"
        )
    except AttributeError:
        raise AttributeError(
            f"La clase '{resolver_name}' no se encontró en el módulo 'fetchr.hosts.{module_name}'"
        )


def load_hosts_config(config_path: Path = None) -> Dict[str, Any]:
    """
    Carga la configuración de hosts desde un archivo YAML.
    
    Args:
        config_path: Ruta al archivo YAML. Si es None, busca hosts_config.yaml en el directorio del módulo.
    
    Returns:
        Diccionario con:
        - 'hosts_handler': Diccionario con la configuración de hosts en el mismo formato que HOSTS_HANLDER
        - 'upload_flix_hosts': Lista de hosts de UploadFlix
        - 'supported_hosts': Lista de hosts soportados (ordenados por prioridad)
        - 'pass_through_hosts': Lista de hosts de paso directo
    """
    if config_path is None:
        # Buscar el archivo en la carpeta padre (donde está pyproject.toml)
        # __file__ está en fetchr/fetchr/config_loader.py, subimos un nivel para llegar a fetchr/
        config_path = Path(__file__).parent.parent / "hosts_config.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Obtener la lista de hosts de UploadFlix
    upload_flix_hosts = config.get("upload_flix_hosts", [])
    upload_flix_template = config.get("hosts", {}).get("upload_flix_template", {})
    
    # Obtener lista de hosts soportados (con prioridad)
    supported_hosts = config.get("supported_hosts", [])
    
    # Expandir supported_hosts: insertar upload_flix_hosts donde corresponda
    # Buscar si hay un marcador o insertar antes del último elemento
    expanded_supported = []
    for host in supported_hosts:
        if host == "upload_flix_hosts":  # Marcador para insertar hosts de UploadFlix
            expanded_supported.extend(upload_flix_hosts)
        else:
            expanded_supported.append(host)
    
    # Si no hay marcador, añadir upload_flix_hosts antes del último elemento
    if "upload_flix_hosts" not in supported_hosts:
        # Insertar antes del último elemento
        if expanded_supported:
            expanded_supported = expanded_supported[:-1] + upload_flix_hosts + [expanded_supported[-1]]
        else:
            expanded_supported = upload_flix_hosts
    
    # Obtener pass_through_hosts
    pass_through_hosts = config.get("pass_through_hosts", [])
    
    # Construir el diccionario de hosts
    hosts_config = {}
    
    # Procesar cada host en la configuración
    for host, host_config in config.get("hosts", {}).items():
        # Saltar el template de upload_flix
        if host == "upload_flix_template":
            continue
        
        # Validar que el host tiene un resolver definido
        if "resolver" not in host_config:
            raise ValueError(f"Host '{host}' no tiene un resolver definido en la configuración")
        
        # Procesar configuración especial de anonfile.de
        if host == "anonfile.de":
            use_premium = bool(os.getenv('ANONFILE_USE_PREMIUM'))
            resolver_name = host_config["resolver"]
            
            processed_config = {
                "download_with_aria2c": host_config.get("download_with_aria2c", False),
                "resolver": _get_resolver_class(resolver_name),
                "max_connections": host_config.get("max_connections_premium" if use_premium else "max_connections_free"),
                "max_concurrent": host_config.get("max_concurrent_premium" if use_premium else "max_concurrent_free"),
                "use_random_proxy": host_config.get("use_random_proxy_premium" if use_premium else "use_random_proxy_free"),
            }
        elif host == "1fichier.com":
            use_realdebrid = bool(os.getenv('REALDEBRID_BEARER_TOKEN') or os.getenv('FETCHR_REALDEBRID_TOKEN'))
            resolver_name = host_config["resolver"]
            
            processed_config = {
                "download_with_aria2c": host_config.get("download_with_aria2c", False),
                "resolver": _get_resolver_class(resolver_name),
                "max_connections": host_config.get("max_connections_realdebrid" if use_realdebrid else "max_connections_free"),
                "max_concurrent": host_config.get("max_concurrent_realdebrid" if use_realdebrid else "max_concurrent_free"),
            }
        else:
            # Procesar configuración normal
            processed_config = {}
            for key, value in host_config.items():
                if key == "resolver":
                    # Cargar la clase del resolver dinámicamente
                    processed_config[key] = _get_resolver_class(value)
                else:
                    processed_config[key] = value
        
        hosts_config[host] = processed_config
    
    # Expandir configuración de UploadFlix para todos los hosts
    for host in upload_flix_hosts:
        processed_config = {}
        for key, value in upload_flix_template.items():
            if key == "resolver":
                processed_config[key] = _get_resolver_class(value)
            else:
                processed_config[key] = value
        hosts_config[host] = processed_config
    
    return {
        "hosts_handler": hosts_config,
        "upload_flix_hosts": upload_flix_hosts,
        "supported_hosts": expanded_supported,
        "pass_through_hosts": pass_through_hosts,
    }
