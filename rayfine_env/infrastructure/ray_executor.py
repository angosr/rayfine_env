"""Ray cluster connection and remote execution"""

import os
import ray
import time
from typing import Dict, Optional, Any

from ..utils.exceptions import RayConnectionError, RayExecutionError
from ..utils.logger import logger


@ray.remote
class _EnvActor:
    """
    Wrapper Actor that loads user's /app/env.py module
    and exposes its functions for remote execution
    """
    
    def __init__(self, env_vars: Optional[Dict[str, str]] = None):
        import os
        import sys
        import importlib.util
        
        # Set environment variables
        if env_vars:
            for key, value in env_vars.items():
                os.environ[key] = value
        
        # Load /app/env.py module
        env_path = "/app/env.py"
        spec = importlib.util.spec_from_file_location("user_env", env_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {env_path}")
        
        self.user_module = importlib.util.module_from_spec(spec)
        sys.modules["user_env"] = self.user_module
        spec.loader.exec_module(self.user_module)
        
        # Check if module has Actor class (legacy support)
        if hasattr(self.user_module, "Actor"):
            self.user_actor = self.user_module.Actor()
        else:
            self.user_actor = None
    
    def call_method(self, method_name: str, *args, **kwargs):
        """
        Call a method from user's env.py
        
        Priority:
        1. If Actor class exists, call Actor().method_name()
        2. Otherwise, call module-level function method_name()
        
        Handles both sync and async methods.
        """
        import asyncio
        import inspect
        
        # Try Actor class method first (legacy)
        if self.user_actor and hasattr(self.user_actor, method_name):
            method = getattr(self.user_actor, method_name)
            if inspect.iscoroutinefunction(method):
                return asyncio.run(method(*args, **kwargs))
            return method(*args, **kwargs)
        
        # Try module-level function
        if hasattr(self.user_module, method_name):
            func = getattr(self.user_module, method_name)
            if callable(func):
                if inspect.iscoroutinefunction(func):
                    return asyncio.run(func(*args, **kwargs))
                return func(*args, **kwargs)
        
        raise AttributeError(
            f"Method '{method_name}' not found in /app/env.py. "
            f"Available: {self._get_available_methods()}"
        )
    
    def _get_available_methods(self):
        """Get list of available methods"""
        methods = []
        
        # From Actor class
        if self.user_actor:
            methods.extend([
                name for name in dir(self.user_actor)
                if not name.startswith('_') and callable(getattr(self.user_actor, name))
            ])
        
        # From module level
        methods.extend([
            name for name in dir(self.user_module)
            if not name.startswith('_') and callable(getattr(self.user_module, name))
        ])
        
        return sorted(set(methods))
    
    def list_methods(self):
        """List all available methods"""
        return self._get_available_methods()


class RayExecutor:
    """Manages Ray cluster connection and remote Actor execution"""
    
    def __init__(self, ray_address: str, connection_timeout: int = 30):
        """
        Initialize Ray connection
        
        Args:
            ray_address: Ray cluster address (e.g., "ray://127.0.0.1:10001")
            connection_timeout: Maximum seconds to wait for connection
        """
        self.ray_address = ray_address
        self.connected = False
        self._actor_handle = None
        
        self._connect(timeout=connection_timeout)
    
    def _connect(self, timeout: int) -> None:
        """
        Connect to Ray cluster
        
        Args:
            timeout: Connection timeout in seconds
        """
        start = time.time()
        last_error = None
        
        # Set environment variable to ignore version mismatch
        os.environ["RAY_IGNORE_VERSION_MISMATCH"] = "1"
        
        logger.debug(f"Connecting to Ray cluster at {self.ray_address}")
        
        while time.time() - start < timeout:
            try:
                # Initialize Ray client with version mismatch ignored
                ray.init(
                    address=self.ray_address,
                    ignore_reinit_error=True,
                    logging_level="ERROR",
                )
                
                # Verify connection
                ray.cluster_resources()
                
                self.connected = True
                return
                
            except Exception as e:
                last_error = e
                logger.debug(f"Connection attempt failed: {e}")
                time.sleep(1)
        
        raise RayConnectionError(
            f"Failed to connect to Ray at {self.ray_address} after {timeout}s: {last_error}"
        )
    
    def create_actor(
        self,
        env_vars: Optional[Dict[str, str]] = None,
        actor_name: Optional[str] = None
    ) -> Any:
        """
        Create Ray Actor that loads /app/env.py
        
        The Actor will:
        1. Set environment variables
        2. Import /app/env.py module
        3. Expose all callable attributes for remote execution
        
        Args:
            env_vars: Environment variables to set in Actor
            actor_name: Optional Actor name for debugging
            
        Returns:
            Ray Actor handle
        """
        try:
            # Create Actor instance using module-level class
            actor_options = {}
            if actor_name:
                actor_options["name"] = actor_name
            
            self._actor_handle = _EnvActor.options(**actor_options).remote(env_vars)
            return self._actor_handle
            
        except Exception as e:
            raise RayExecutionError(f"Failed to create Actor: {e}")
    
    def call_method(
        self,
        method_name: str,
        *args,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Call a method on the Ray Actor
        
        Args:
            method_name: Name of method to call
            *args: Positional arguments
            timeout: Optional timeout in seconds
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        if not self._actor_handle:
            raise RayExecutionError("No Actor created. Call create_actor() first")
        
        try:
            logger.debug(f"Calling Actor method: {method_name}")
            
            # Call method remotely
            future = self._actor_handle.call_method.remote(method_name, *args, **kwargs)
            
            # Wait for result
            if timeout:
                result = ray.get(future, timeout=timeout)
            else:
                result = ray.get(future)
            
            logger.debug(f"Method {method_name} completed successfully")
            return result
            
        except ray.exceptions.RayTaskError as e:
            # Extract original exception from Ray wrapper
            raise RayExecutionError(f"Actor method '{method_name}' failed: {e}")
        except Exception as e:
            raise RayExecutionError(f"Failed to call method '{method_name}': {e}")
    
    def list_methods(self) -> list:
        """
        List all available methods in user's env.py
        
        Returns:
            List of method names
        """
        if not self._actor_handle:
            raise RayExecutionError("No Actor created. Call create_actor() first")
        
        try:
            future = self._actor_handle.list_methods.remote()
            return ray.get(future)
        except Exception as e:
            raise RayExecutionError(f"Failed to list methods: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from Ray cluster"""
        try:
            if self.connected:
                logger.debug("Disconnecting from Ray cluster")
                ray.shutdown()
                self.connected = False
                self._actor_handle = None
        except Exception as e:
            logger.warning(f"Error during Ray disconnect: {e}")
    
    def __del__(self):
        """Cleanup on deletion"""
        self.disconnect()