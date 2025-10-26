"""Environment wrapper with dynamic method dispatch"""

import time
from typing import Dict, Optional, Any

from ..backends.base import AbstractBackend
from ..utils.exceptions import EnvironmentError
from ..utils.logger import logger


class EnvironmentWrapper:
    """
    User-facing wrapper for environment interaction
    
    Provides dynamic method dispatch via __getattr__ to expose
    all methods from the environment's env.py file.
    
    Example:
        env = load_env(image="affine:latest", env_vars={"CHUTES_API_KEY": "xxx"})
        result = env.evaluate(task_type="sat", num_samples=5)
        env.cleanup()
    """
    
    def __init__(
        self,
        backend: AbstractBackend,
    ):
        """
        Initialize environment wrapper
        
        Args:
            backend: Backend instance (LocalBackend or RemoteBackend)
            env_id: Unique environment identifier
        """
        self._backend = backend
        self.name = backend.name
        # Backend is ready immediately after initialization
        self._is_ready = backend.is_ready()
        logger.debug(f"Created EnvironmentWrapper '{self.name}' (ready: {self._is_ready})")
    
    def cleanup(self) -> None:
        """
        Clean up environment resources
        
        Stops containers, disconnects Ray, and frees resources.
        Should be called when done using the environment.
        """
        try:
            logger.debug(f"Cleaning up environment '{self.name}'")
            self._backend.cleanup()
            self._is_ready = False
            logger.debug(f"Environment '{self.name}' cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup of '{self.name}': {e}")
    
    def list_methods(self) -> list:
        """
        List all available methods in the environment
        
        Returns:
            List of method names that can be called
        """
        if not self._is_ready:
            raise EnvironmentError(
                f"Environment '{self.name}' not ready."
            )
        
        try:
            return self._backend.list_methods()
        except Exception as e:
            raise EnvironmentError(f"Failed to list methods: {e}")
    
    def is_ready(self) -> bool:
        """
        Check if environment is ready for method calls
        
        Returns:
            True if backend is ready
        """
        return self._is_ready and self._backend.is_ready()
    
    def __getattr__(self, name: str):
        """
        Dynamic method dispatch
        
        Intercepts method calls and forwards them to the backend.
        This allows calling any method defined in env.py without
        hardcoding method names.
        
        Args:
            name: Method name
            
        Returns:
            Callable that executes the remote method
            
        Example:
            env.evaluate(...)  # Calls Actor.evaluate() or evaluate()
            env.custom_func()  # Calls any function from env.py
        """
        # Prevent infinite recursion for private attributes
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        
        # Check if environment is ready
        if not self._is_ready:
            raise EnvironmentError(
                f"Environment '{self.name}' not ready."
            )
        
        # Return a callable that will invoke the remote method
        def method_caller(*args, timeout: Optional[int] = None, **kwargs):
            """
            Execute remote method
            
            Args:
                *args: Positional arguments
                timeout: Optional timeout in seconds
                **kwargs: Keyword arguments
                
            Returns:
                Method result
            """
            try:
                logger.debug(f"Calling method '{name}' on environment '{self.name}'")
                
                result = self._backend.call_method(
                    name,
                    *args,
                    timeout=timeout,
                    **kwargs
                )
                
                logger.debug(f"Method '{name}' completed successfully")
                return result
                
            except Exception as e:
                raise EnvironmentError(
                    f"Method '{name}' failed on environment '{self.name}': {e}"
                )
        
        return method_caller
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatic cleanup"""
        self.cleanup()
    
    def __del__(self):
        """Cleanup on deletion"""
        if self._is_ready:
            self.cleanup()
    
    def __repr__(self) -> str:
        """String representation"""
        status = "ready" if self.is_ready() else "not ready"
        return f"<EnvironmentWrapper '{self.name}' ({status})>"