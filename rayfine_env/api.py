"""Public API for rayfine-env"""

import time
from typing import Optional, Dict, Any
from pathlib import Path

from .backends import LocalBackend, RemoteBackend
from .infrastructure import ImageBuilder
from .core import EnvironmentWrapper, get_registry
from .utils.logger import logger
from .utils.exceptions import ValidationError


def build_image_from_env(
    env_path: str,
    image_tag: str,
    nocache: bool = False,
    quiet: bool = False
) -> str:
    """
    Build Docker image from environment definition
    
    Args:
        env_path: Path to environment directory (must contain env.py and Dockerfile)
        image_tag: Image tag (e.g., "affine:latest")
        nocache: Don't use build cache
        quiet: Suppress build output
        
    Returns:
        Built image ID
        
    Example:
        >>> build_image_from_env("environments/affine", "affine:latest")
        'sha256:abc123...'
    """
    try:
        logger.info(f"Building image '{image_tag}' from '{env_path}'")
        
        builder = ImageBuilder()
        image_id = builder.build_from_env(
            env_path=env_path,
            image_tag=image_tag,
            nocache=nocache,
            quiet=quiet
        )
        
        logger.info(f"Image '{image_tag}' built successfully")
        return image_id
        
    except Exception as e:
        logger.error(f"Failed to build image: {e}")
        raise


def load_env(
    image: str,
    mode: str = "local",
    container_name: Optional[str] = None,
    ray_port: int = 10001,
    **backend_kwargs
) -> EnvironmentWrapper:
    """
    Load and start an environment
    
    Args:
        image: Docker image name (for local mode) or environment ID (for remote mode)
        mode: Execution mode - "local" or "remote"
        container_name: Optional container name (local mode only)
        ray_port: Ray client port (local mode only, default: 10001)
        **backend_kwargs: Additional backend-specific parameters
        
    Returns:
        EnvironmentWrapper instance
        
    Example (local mode):
        >>> env = load_env(image="affine:latest")
        >>> env.setup(CHUTES_API_KEY="xxx")
        >>> result = env.evaluate(task_type="sat", num_samples=5)
        >>> env.cleanup()
        
    Example (remote mode - not yet implemented):
        >>> env = load_env(
        ...     image="affine-v1",
        ...     mode="remote",
        ...     api_endpoint="https://api.example.com",
        ...     api_key="xxx"
        ... )
    """
    try:
        # Generate unique environment ID
        timestamp = int(time.time() * 1000)
        env_id = f"{image.replace(':', '-')}_{timestamp}"
        
        logger.info(f"Loading environment '{env_id}' in {mode} mode")
        
        # Create appropriate backend
        if mode == "local":
            backend = LocalBackend(
                image=image,
                container_name=container_name,
                ray_port=ray_port,
                **backend_kwargs
            )
        elif mode == "remote":
            backend = RemoteBackend(
                environment_id=image,
                **backend_kwargs
            )
        else:
            raise ValidationError(f"Invalid mode: {mode}. Must be 'local' or 'remote'")
        
        # Create wrapper
        wrapper = EnvironmentWrapper(backend=backend, env_id=env_id)
        
        # Register in global registry
        registry = get_registry()
        registry.register(env_id, wrapper)
        
        logger.info(f"Environment '{env_id}' loaded successfully")
        return wrapper
        
    except Exception as e:
        logger.error(f"Failed to load environment: {e}")
        raise


def list_active_environments() -> list:
    """
    List all currently active environments
    
    Returns:
        List of environment IDs
        
    Example:
        >>> list_active_environments()
        ['affine-latest_1234567890', 'custom-v1_1234567891']
    """
    registry = get_registry()
    return registry.list_all()


def cleanup_all_environments() -> None:
    """
    Clean up all active environments
    
    Stops all containers, disconnects Ray, and frees resources.
    Automatically called on program exit.
    
    Example:
        >>> cleanup_all_environments()
    """
    logger.info("Cleaning up all environments")
    registry = get_registry()
    registry.cleanup_all()


def get_environment(env_id: str) -> Optional[EnvironmentWrapper]:
    """
    Get an environment by ID
    
    Args:
        env_id: Environment identifier
        
    Returns:
        EnvironmentWrapper instance or None if not found
        
    Example:
        >>> env = get_environment('affine-latest_1234567890')
    """
    registry = get_registry()
    return registry.get(env_id)