"""Local backend - Docker + Ray execution"""

import time
from typing import Dict, Optional, Any

from .base import AbstractBackend
from ..infrastructure import DockerManager, RayExecutor
from ..utils.exceptions import BackendError, SetupError
from ..utils.logger import logger
from ..utils.config import Config


class LocalBackend(AbstractBackend):
    """
    Local execution backend using Docker containers and Ray
    
    Lifecycle:
    1. __init__: Start Docker container with Ray cluster
    2. setup(): Connect to Ray and create Actor with env vars
    3. call_method(): Execute methods via Ray Actor
    4. cleanup(): Stop container and disconnect Ray
    """
    
    def __init__(
        self,
        image: str,
        container_name: Optional[str] = None,
        ray_port: int = 10001,
        **docker_kwargs
    ):
        """
        Initialize backend - starts Docker container
        
        Args:
            image: Docker image name
            container_name: Optional container name
            ray_port: Ray client port
            **docker_kwargs: Additional Docker container options
        """
        self.image = image
        self.container_name = container_name or f"rayfine-{image.replace(':', '-')}-{int(time.time())}"
        self.ray_port = ray_port
        
        self._container = None
        self._docker_manager = None
        self._ray_executor = None
        self._is_setup = False
        
        # Start container
        self._start_container(**docker_kwargs)
    
    def _start_container(self, **docker_kwargs) -> None:
        """Start Docker container with Ray cluster"""
        try:
            logger.debug(f"Starting container for image '{self.image}'")
            
            # Initialize Docker manager
            self._docker_manager = DockerManager()
            
            # Prepare container configuration
            container_config = {
                "image": self.image,
                "name": self.container_name,
                "ports": {self.ray_port: self.ray_port},  # Expose Ray client port
                "detach": True,
                **docker_kwargs
            }
            
            # Start container
            self._container = self._docker_manager.start_container(**container_config)
            
            # Wait for Ray to be ready
            logger.debug(f"Waiting for Ray cluster to start on port {self.ray_port}")
            if not self._docker_manager.wait_for_port(
                self._container,
                self.ray_port,
                timeout=Config.RAY_START_TIMEOUT
            ):
                raise BackendError(
                    f"Ray cluster did not start within {Config.RAY_START_TIMEOUT}s. "
                    "Check container logs for errors."
                )
            
            logger.debug("Container started and Ray cluster ready")
            
        except Exception as e:
            # Cleanup on failure
            if self._container:
                try:
                    self._docker_manager.stop_container(self._container)
                except:
                    pass
            raise BackendError(f"Failed to start container: {e}")
    
    def setup(self, env_vars: Optional[Dict[str, str]] = None) -> None:
        """
        Connect to Ray and create Actor with environment variables
        
        Args:
            env_vars: Environment variables to inject into Actor
        """
        if self._is_setup:
            logger.warning("Backend already setup, skipping")
            return
        
        try:
            # Get Ray address
            ray_address = f"ray://127.0.0.1:{self.ray_port}"
            
            # Connect to Ray cluster
            self._ray_executor = RayExecutor(
                ray_address=ray_address,
                connection_timeout=Config.RAY_CONNECTION_TIMEOUT
            )
            
            # Create Actor with environment variables
            actor_name = f"env_actor_{self.container_name}"
            self._ray_executor.create_actor(
                env_vars=env_vars,
                actor_name=actor_name
            )
            
            self._is_setup = True
            logger.debug("Backend setup completed")
            
        except Exception as e:
            raise SetupError(f"Failed to setup backend: {e}")
    
    def call_method(
        self,
        method_name: str,
        *args,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Call a method from env.py via Ray Actor
        
        Args:
            method_name: Method name to call
            *args: Positional arguments
            timeout: Optional timeout in seconds
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        if not self._is_setup:
            raise SetupError(
                "Backend not setup. Call setup() before calling methods."
            )
        
        try:
            return self._ray_executor.call_method(
                method_name,
                *args,
                timeout=timeout,
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
        if not self._is_setup:
            raise SetupError(
                "Backend not setup. Call setup() before listing methods."
            )
        
        try:
            return self._ray_executor.list_methods()
        except Exception as e:
            raise BackendError(f"Failed to list methods: {e}")
    
    def cleanup(self) -> None:
        """Stop container and disconnect Ray"""
        logger.debug(f"Cleaning up backend for container {self.container_name}")
        
        # Disconnect Ray
        if self._ray_executor:
            try:
                self._ray_executor.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting Ray: {e}")
            finally:
                self._ray_executor = None
        
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