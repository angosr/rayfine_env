"""Local backend - Docker + HTTP execution"""

import time
from datetime import datetime
from typing import Dict, Optional, Any

from .base import AbstractBackend
from ..infrastructure import DockerManager, HTTPExecutor, EnvType
from ..utils.exceptions import BackendError, SetupError
from ..utils.logger import logger
from ..utils.config import Config


class LocalBackend(AbstractBackend):
    """
    Local execution backend using Docker containers and HTTP
    
    Lifecycle:
    1. __init__: Start Docker container with HTTP server
    2. call_method(): Execute methods via HTTP API
    3. cleanup(): Stop container
    """
    
    def __init__(
        self,
        image: str,
        container_name: Optional[str] = None,
        http_port: int = 8000,
        env_vars: Optional[Dict[str, str]] = None,
        env_type_override: Optional[str] = None,
        **docker_kwargs
    ):
        """
        Initialize backend - starts Docker container
        
        Args:
            image: Docker image name
            container_name: Optional container name
            http_port: HTTP server port
            env_vars: Environment variables to pass to container
            env_type_override: Override environment type detection
            **docker_kwargs: Additional Docker container options
        """
        self.image = image
        # Generate human-readable timestamp: YYYYMMDD-HHMMSS
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.name = container_name or f"{image.replace(':', '-')}-{timestamp}"
        self.http_port = http_port
        
        self._container = None
        self._docker_manager = None
        self._http_executor = None
        self._is_setup = False
        self._env_type = None
        self._env_type_override = env_type_override
        
        # Start container with env vars
        self._start_container(env_vars=env_vars, **docker_kwargs)
    
    def _start_container(self, env_vars: Optional[Dict[str, str]] = None, **docker_kwargs) -> None:
        """Start Docker container with HTTP server
        
        Args:
            env_vars: Environment variables to pass to container
            **docker_kwargs: Additional Docker options
        """
        try:
            logger.debug(f"Starting container for image '{self.image}'")
            
            # Get environment type (use override if provided)
            if self._env_type_override:
                self._env_type = self._env_type_override
                logger.info(f"Environment type (manual): {self._env_type}")
            else:
                self._env_type = self._get_env_type()
                logger.info(f"Environment type (detected): {self._env_type}")
            
            # Initialize Docker manager
            self._docker_manager = DockerManager()
            
            # Merge environment variables
            if env_vars:
                if "environment" in docker_kwargs:
                    docker_kwargs["environment"].update(env_vars)
                else:
                    docker_kwargs["environment"] = env_vars
            
            # Prepare container configuration
            container_config = {
                "image": self.image,
                "name": self.name,
                "ports": {self.http_port: self.http_port},  # Expose HTTP port
                "detach": True,
                "restart_policy": {"Name": "always"},  # Auto-restart on failure
                **docker_kwargs
            }
            
            # Start container
            self._container = self._docker_manager.start_container(**container_config)
            
            # Create HTTP executor
            self._http_executor = HTTPExecutor(
                base_url=f"http://localhost:{self.http_port}",
                env_type=self._env_type,
                timeout=600
            )
            
            # Wait for HTTP server to be ready
            # http_based environments may take longer to start (loading dependencies)
            timeout = 120 if self._env_type == EnvType.HTTP_BASED else 60
            logger.debug(f"Waiting for HTTP server on port {self.http_port} (timeout={timeout}s)")
            if not self._wait_for_http_ready(timeout=timeout):
                raise BackendError(
                    f"HTTP server did not start within {timeout}s. "
                    "Check container logs for errors."
                )
            
            # Mark as setup - HTTP backend is ready after container starts
            self._is_setup = True
            logger.debug("Container started and HTTP server ready")
            
        except Exception as e:
            # Cleanup on failure
            if self._container:
                try:
                    self._docker_manager.stop_container(self._container)
                except:
                    pass
            raise BackendError(f"Failed to start container: {e}")
    
    def _get_env_type(self) -> str:
        """Get environment type from image labels"""
        try:
            from ..infrastructure import DockerManager
            docker_mgr = DockerManager()
            img = docker_mgr.client.images.get(self.image)
            labels = img.labels or {}
            env_type = labels.get("rayfine.env.type", EnvType.FUNCTION_BASED)
            logger.debug(f"Detected env_type from image labels: {env_type}")
            return env_type
        except Exception as e:
            logger.warning(f"Failed to get env type from image: {e}, defaulting to function_based")
            return EnvType.FUNCTION_BASED
    
    def _wait_for_http_ready(self, timeout: int = 60) -> bool:
        """Wait for HTTP server to be ready"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if self._http_executor.health_check():
                    return True
            except Exception as e:
                logger.debug(f"Health check failed: {e}")
            time.sleep(1)
        return False
    
    def call_method(
        self,
        method_name: str,
        *args,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Call a method from env.py via HTTP
        
        Args:
            method_name: Method name to call
            *args: Positional arguments
            timeout: Optional timeout in seconds (not used currently)
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        try:
            return self._http_executor.call_method(
                method_name,
                *args,
                **kwargs
            )
        except Exception as e:
            raise BackendError(f"Method call failed: {e}")
    
    def list_methods(self) -> list:
        """
        List all available methods from env.py
        
        Returns:
            List of method names
        """
        try:
            return self._http_executor.list_methods()
        except Exception as e:
            raise BackendError(f"Failed to list methods: {e}")
    
    def cleanup(self) -> None:
        """Stop container and close HTTP client"""
        logger.debug(f"Cleaning up backend for container {self.name}")
        
        # Close HTTP client
        if self._http_executor:
            try:
                self._http_executor.close()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
            finally:
                self._http_executor = None
        
        # Stop container
        if self._container and self._docker_manager:
            try:
                self._docker_manager.stop_container(self._container)
            except Exception as e:
                logger.warning(f"Error stopping container: {e}")
            finally:
                self._container = None
        
        self._is_setup = False
        logger.debug("Backend cleanup completed")
    
    def is_ready(self) -> bool:
        """
        Check if backend is ready for method calls
        
        Returns:
            True if setup completed
        """
        return self._is_setup
    
    def get_container_logs(self, tail: int = 100) -> str:
        """
        Get container logs for debugging
        
        Args:
            tail: Number of lines to return
            
        Returns:
            Log output
        """
        if not self._container:
            return ""
        
        try:
            logs = self._container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return ""
    
    def __del__(self):
        """Cleanup on deletion"""
        self.cleanup()