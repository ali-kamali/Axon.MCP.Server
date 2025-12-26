"""Docker Compose parser for extracting service definitions and infrastructure topology.

This parser supports Docker Compose v2 and v3 formats and extracts:
- Service definitions (name, image, ports, networks)
- Environment variables and configuration
- Service dependencies (depends_on, links)
- Network topology
- Volume mappings
"""

import yaml
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DockerComposeParser:
    """Parser for docker-compose.yml files."""

    def __init__(self):
        """Initialize the Docker Compose parser."""
        self.supported_versions = ["2", "2.0", "2.1", "2.2", "2.3", "2.4", "3", "3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9"]

    async def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse a docker-compose.yml file.
        
        Args:
            file_path: Path to docker-compose.yml file
            
        Returns:
            Dictionary with parsed services, networks, and volumes
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            if not content:
                logger.warning("docker_compose_empty", file_path=str(file_path))
                return {"services": [], "networks": [], "volumes": []}
            
            # Determine version
            version = content.get("version", "1")
            if version not in self.supported_versions and version != "1":
                logger.warning("docker_compose_unsupported_version", version=version, file_path=str(file_path))
            
            # Parse services
            services = self._parse_services(content.get("services", {}), file_path)
            
            # Parse networks
            networks = self._parse_networks(content.get("networks", {}))
            
            # Parse volumes
            volumes = self._parse_volumes(content.get("volumes", {}))
            
            logger.info("docker_compose_parsed", 
                       file_path=str(file_path),
                       service_count=len(services),
                       network_count=len(networks),
                       volume_count=len(volumes))
            
            return {
                "version": version,
                "services": services,
                "networks": networks,
                "volumes": volumes,
                "file_path": str(file_path)
            }
            
        except yaml.YAMLError as e:
            logger.error("docker_compose_yaml_error", file_path=str(file_path), error=str(e))
            return {"services": [], "networks": [], "volumes": []}
        except Exception as e:
            logger.error("docker_compose_parse_error", file_path=str(file_path), error=str(e))
            return {"services": [], "networks": [], "volumes": []}

    def _parse_services(self, services_dict: Dict[str, Any], file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse services section from docker-compose.yml.
        
        Args:
            services_dict: Services dictionary from YAML
            file_path: Path to the compose file
            
        Returns:
            List of parsed service definitions
        """
        services = []
        
        for service_name, service_config in services_dict.items():
            if not isinstance(service_config, dict):
                logger.warning("docker_compose_invalid_service", service_name=service_name)
                continue
            
            service = {
                "service_name": service_name,
                "image": service_config.get("image"),
                "build": self._parse_build(service_config.get("build")),
                "container_name": service_config.get("container_name"),
                "ports": self._parse_ports(service_config.get("ports", [])),
                "environment": self._parse_environment(service_config.get("environment", {})),
                "volumes": self._parse_service_volumes(service_config.get("volumes", [])),
                "networks": self._parse_service_networks(service_config.get("networks", [])),
                "depends_on": self._parse_depends_on(service_config.get("depends_on", [])),
                "links": service_config.get("links", []),
                "command": service_config.get("command"),
                "entrypoint": service_config.get("entrypoint"),
                "working_dir": service_config.get("working_dir"),
                "user": service_config.get("user"),
                "restart": service_config.get("restart"),
                "healthcheck": service_config.get("healthcheck"),
                "labels": service_config.get("labels", {}),
                "expose": service_config.get("expose", []),
                "extra_hosts": service_config.get("extra_hosts", []),
            }
            
            services.append(service)
        
        return services

    def _parse_build(self, build_config: Any) -> Optional[Dict[str, Any]]:
        """Parse build configuration."""
        if not build_config:
            return None
        
        if isinstance(build_config, str):
            return {"context": build_config}
        
        if isinstance(build_config, dict):
            return {
                "context": build_config.get("context", "."),
                "dockerfile": build_config.get("dockerfile"),
                "args": build_config.get("args", {}),
                "target": build_config.get("target"),
            }
        
        return None

    def _parse_ports(self, ports_config: List[Any]) -> List[Dict[str, Any]]:
        """
        Parse ports configuration.
        
        Supports formats:
        - "8080:80"
        - "8080:80/tcp"
        - {target: 80, published: 8080, protocol: tcp}
        """
        parsed_ports = []
        
        for port in ports_config:
            if isinstance(port, str):
                # Parse "host:container" or "host:container/protocol" format
                match = re.match(r'^(\d+):(\d+)(?:/(tcp|udp))?$', port)
                if match:
                    parsed_ports.append({
                        "host": int(match.group(1)),
                        "container": int(match.group(2)),
                        "protocol": match.group(3) or "tcp"
                    })
                else:
                    # Single port (container only)
                    try:
                        parsed_ports.append({
                            "container": int(port),
                            "protocol": "tcp"
                        })
                    except ValueError:
                        logger.warning("docker_compose_invalid_port", port=port)
            
            elif isinstance(port, dict):
                # Long format
                parsed_ports.append({
                    "host": port.get("published"),
                    "container": port.get("target"),
                    "protocol": port.get("protocol", "tcp"),
                    "mode": port.get("mode")
                })
        
        return parsed_ports

    def _parse_environment(self, env_config: Any) -> Dict[str, str]:
        """
        Parse environment variables.
        
        Supports formats:
        - List: ["KEY=value", "KEY2=value2"]
        - Dict: {KEY: value, KEY2: value2}
        """
        if isinstance(env_config, dict):
            return {k: str(v) if v is not None else "" for k, v in env_config.items()}
        
        if isinstance(env_config, list):
            env_dict = {}
            for item in env_config:
                if isinstance(item, str) and "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key] = value
                else:
                    # Environment variable without value (will be taken from host)
                    env_dict[item] = ""
            return env_dict
        
        return {}

    def _parse_service_volumes(self, volumes_config: List[Any]) -> List[Dict[str, Any]]:
        """
        Parse volume mappings.
        
        Supports formats:
        - "/host/path:/container/path"
        - "/host/path:/container/path:ro"
        - {type: bind, source: /host/path, target: /container/path}
        """
        parsed_volumes = []
        
        for volume in volumes_config:
            if isinstance(volume, str):
                # Parse "source:target" or "source:target:mode" format
                parts = volume.split(":")
                if len(parts) >= 2:
                    parsed_volumes.append({
                        "source": parts[0],
                        "target": parts[1],
                        "mode": parts[2] if len(parts) > 2 else "rw",
                        "type": "bind" if parts[0].startswith("/") or parts[0].startswith(".") else "volume"
                    })
            
            elif isinstance(volume, dict):
                # Long format
                parsed_volumes.append({
                    "type": volume.get("type", "volume"),
                    "source": volume.get("source"),
                    "target": volume.get("target"),
                    "mode": "ro" if volume.get("read_only") else "rw",
                    "volume_options": volume.get("volume", {})
                })
        
        return parsed_volumes

    def _parse_service_networks(self, networks_config: Any) -> List[str]:
        """
        Parse networks configuration.
        
        Supports formats:
        - List: ["network1", "network2"]
        - Dict: {network1: {aliases: [alias1]}}
        """
        if isinstance(networks_config, list):
            return networks_config
        
        if isinstance(networks_config, dict):
            return list(networks_config.keys())
        
        return []

    def _parse_depends_on(self, depends_on_config: Any) -> List[str]:
        """
        Parse depends_on configuration.
        
        Supports formats:
        - List: ["service1", "service2"]
        - Dict: {service1: {condition: service_healthy}}
        """
        if isinstance(depends_on_config, list):
            return depends_on_config
        
        if isinstance(depends_on_config, dict):
            return list(depends_on_config.keys())
        
        return []

    def _parse_networks(self, networks_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse networks section from docker-compose.yml."""
        networks = []
        
        for network_name, network_config in networks_dict.items():
            if network_config is None:
                network_config = {}
            
            network = {
                "network_name": network_name,
                "driver": network_config.get("driver", "bridge"),
                "external": network_config.get("external", False),
                "ipam": network_config.get("ipam"),
                "labels": network_config.get("labels", {}),
            }
            
            networks.append(network)
        
        return networks

    def _parse_volumes(self, volumes_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse volumes section from docker-compose.yml."""
        volumes = []
        
        for volume_name, volume_config in volumes_dict.items():
            if volume_config is None:
                volume_config = {}
            
            volume = {
                "volume_name": volume_name,
                "driver": volume_config.get("driver", "local"),
                "external": volume_config.get("external", False),
                "labels": volume_config.get("labels", {}),
            }
            
            volumes.append(volume)
        
        return volumes

    def extract_service_urls(self, service: Dict[str, Any]) -> List[str]:
        """
        Extract potential service URLs from a service definition.
        
        Args:
            service: Parsed service dictionary
            
        Returns:
            List of service URLs (e.g., ["http://service-name:8080"])
        """
        urls = []
        service_name = service.get("service_name")
        
        if not service_name:
            return urls
        
        # Extract from ports
        for port in service.get("ports", []):
            container_port = port.get("container")
            if container_port:
                # Assume HTTP for common web ports
                protocol = "http" if container_port in [80, 8080, 3000, 5000] else "tcp"
                if protocol == "http":
                    urls.append(f"http://{service_name}:{container_port}")
        
        # Extract from expose
        for port in service.get("expose", []):
            try:
                port_num = int(port)
                protocol = "http" if port_num in [80, 8080, 3000, 5000] else "tcp"
                if protocol == "http":
                    urls.append(f"http://{service_name}:{port_num}")
            except (ValueError, TypeError):
                pass
        
        return urls
