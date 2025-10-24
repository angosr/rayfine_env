"""Docker container lifecycle management"""

import docker
import time
from typing import Dict, Optional, Any

from ..utils.exceptions import ContainerError, ImageNotFoundError
from ..utils.logger import logger


class DockerManager:
    """Manages Docker container lifecycle operations"""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise ContainerError(f"Failed to connect to Docker daemon: {e}")
    
    def start_container(
        self,
        image: str,
        name: Optional[str] = None,
        ports: Optional[Dict[int, int]] = None,
        detach: bool = True,
        **kwargs
    ) -> Any:
        """
        Start a Docker container
        
        Args:
            image: Docker image name (e.g., "affine:latest")
            name: Optional container name
            ports: Port mapping {container_port: host_port}
            detach: Run container in background
            **kwargs: Additional docker.containers.run() parameters
            
        Returns:
            Container object
            
        Raises:
            ImageNotFoundError: If image doesn't exist
            ContainerError: If container fails to start
        """
        try:
            # Check if image exists
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                raise ImageNotFoundError(f"Image '{image}' not found. Build it first using build_image_from_env()")
            
            # Prepare container configuration
            container_config = {
                "image": image,
                "detach": detach,
                "remove": False,  # Don't auto-remove on exit
                "tty": True,
                "stdin_open": True,
                **kwargs
            }
            
            if name:
                container_config["name"] = name
            
            if ports:
                container_config["ports"] = ports
            
            # Start container
            logger.info(f"Starting container from image '{image}'")
            container = self.client.containers.run(**container_config)
            
            # Wait for container to be running
            container.reload()
            if container.status != "running":
                raise ContainerError(f"Container failed to start: {container.status}")
            
            logger.info(f"Container {container.short_id} started successfully")
            return container
            
        except ImageNotFoundError:
            raise
        except docker.errors.APIError as e:
            raise ContainerError(f"Docker API error: {e}")
        except Exception as e:
            raise ContainerError(f"Failed to start container: {e}")
    
    def stop_container(self, container: Any, timeout: int = 10) -> None:
        """
        Stop and remove a container
        
        Args:
            container: Container object
            timeout: Seconds to wait before killing
        """
        try:
            container_id = container.short_id
            logger.info(f"Stopping container {container_id}")
            
            container.stop(timeout=timeout)
            container.remove(force=True)
            
            logger.info(f"Container {container_id} stopped and removed")
            
        except Exception as e:
            logger.warning(f"Error stopping container: {e}")
            # Try force removal
            try:
                container.remove(force=True)
            except:
                pass
    
    def get_container_ip(self, container: Any) -> str:
        """
        Get container IP address
        
        Args:
            container: Container object
            
        Returns:
            Container IP address
        """
        try:
            container.reload()
            networks = container.attrs["NetworkSettings"]["Networks"]
            # Get first network IP
            for network_name, network_info in networks.items():
                ip = network_info.get("IPAddress")
                if ip:
                    return ip
            
            raise ContainerError("No IP address found for container")
            
        except Exception as e:
            raise ContainerError(f"Failed to get container IP: {e}")
    
    def wait_for_port(
        self,
        container: Any,
        port: int,
        timeout: int = 30,
        interval: float = 0.5
    ) -> bool:
        """
        Wait for a port to be ready inside container
        
        Args:
            container: Container object
            port: Port number to check
            timeout: Maximum seconds to wait
            interval: Check interval in seconds
            
        Returns:
            True if port is ready, False if timeout
        """
        import socket
        
        start = time.time()
        container_ip = self.get_container_ip(container)
        
        logger.debug(f"Waiting for port {port} on {container_ip}")
        
        while time.time() - start < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((container_ip, port))
                sock.close()
                
                if result == 0:
                    logger.debug(f"Port {port} is ready")
                    return True
                    
            except Exception:
                pass
            
            time.sleep(interval)
        
        logger.warning(f"Timeout waiting for port {port}")
        return False
    
    def exec_command(
        self,
        container: Any,
        command: str,
        workdir: Optional[str] = None
    ) -> tuple:
        """
        Execute command inside container
        
        Args:
            container: Container object
            command: Command to execute
            workdir: Working directory
            
        Returns:
            (exit_code, output)
        """
        try:
            exec_config = {"cmd": command, "stdout": True, "stderr": True}
            if workdir:
                exec_config["workdir"] = workdir
            
            exit_code, output = container.exec_run(**exec_config)
            return exit_code, output.decode("utf-8")
            
        except Exception as e:
            raise ContainerError(f"Failed to execute command: {e}")
    
    def cleanup_all(self, name_pattern: Optional[str] = None) -> None:
        """
        Clean up containers matching pattern
        
        Args:
            name_pattern: Only remove containers with names containing this pattern
        """
        try:
            containers = self.client.containers.list(all=True)
            
            for container in containers:
                if name_pattern and name_pattern not in container.name:
                    continue
                
                try:
                    logger.info(f"Cleaning up container {container.short_id}")
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup {container.short_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")