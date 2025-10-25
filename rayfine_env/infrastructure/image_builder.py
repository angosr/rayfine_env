"""Docker image building from environment definitions"""

import docker
import importlib.util
from pathlib import Path
from typing import Optional

from ..utils.exceptions import ImageBuildError, ValidationError
from ..utils.logger import logger


class ImageBuilder:
    """Builds Docker images from environment definitions"""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise ImageBuildError(f"Failed to connect to Docker daemon: {e}")
    
    def build_from_env(
        self,
        env_path: str,
        image_tag: str,
        nocache: bool = False,
        quiet: bool = False,
        buildargs: Optional[dict] = None
    ) -> str:
        """
        Build Docker image from environment directory
        
        Expected directory structure:
            env_path/
                env.py          (required) - Main environment code
                Dockerfile      (required) - Dockerfile definition
                requirements.txt (optional) - Python dependencies
                *.py            (optional) - Additional Python modules
        
        Args:
            env_path: Path to environment directory
            image_tag: Image tag (e.g., "affine:latest")
            nocache: Don't use build cache
            quiet: Suppress build output
            buildargs: Docker build arguments (e.g., {"ENV_NAME": "webshop", "TOOL_NAME": "webshop"})
            
        Returns:
            Built image ID
        """
        env_path = Path(env_path).resolve()
        
        # Validate environment directory
        if not env_path.is_dir():
            raise ValidationError(f"Environment path does not exist: {env_path}")
        
        env_file = env_path / "env.py"
        if not env_file.exists():
            raise ValidationError(
                f"Missing required env.py in {env_path}. "
                "Every environment must have an env.py file."
            )
        
        # Require Dockerfile
        dockerfile_path = env_path / "Dockerfile"
        if not dockerfile_path.exists():
            raise ValidationError(
                f"Missing required Dockerfile in {env_path}. "
                "Every environment must have a Dockerfile. "
                "See environments/affine/Dockerfile for example."
            )
        
        logger.info(f"Using Dockerfile from {dockerfile_path}")
        
        # Auto-resolve buildargs using config.py if exists
        config_path = env_path / "config.py"
        if config_path.exists() and buildargs:
            buildargs = self._resolve_buildargs(config_path, buildargs)
        
        # Build image
        try:
            logger.info(f"Building image '{image_tag}' from {env_path}")
            
            if buildargs:
                logger.info(f"Using build args: {buildargs}")
            
            # Stream build output in real-time
            build_logs = self.client.api.build(
                path=str(env_path),
                tag=image_tag,
                dockerfile="Dockerfile",
                buildargs=buildargs or {},
                nocache=nocache,
                rm=True,
                decode=True
            )
            
            image_id = None
            for log in build_logs:
                if "stream" in log and not quiet:
                    print(log["stream"].rstrip(), flush=True)
                elif "error" in log:
                    print(log["error"].strip(), flush=True)
                    raise ImageBuildError(f"Build failed: {log['error']}")
                elif "aux" in log and "ID" in log["aux"]:
                    image_id = log["aux"]["ID"]
            
            if not image_id:
                raise ImageBuildError("Build completed but no image ID returned")
            
            image = self.client.images.get(image_id)
            logger.info(f"Successfully built image '{image_tag}' ({image.short_id})")
            return image_tag
            
        except docker.errors.BuildError as e:
            error_msg = "Image build failed:\n"
            for log in e.build_log:
                if "error" in log:
                    error_msg += f"  {log['error']}\n"
                elif "stream" in log:
                    error_msg += f"  {log['stream']}"
            raise ImageBuildError(error_msg)
        except Exception as e:
            raise ImageBuildError(f"Failed to build image: {e}")
    
    def _resolve_buildargs(self, config_path: Path, buildargs: dict) -> dict:
        """
        Resolve build arguments using config.py
        
        Args:
            config_path: Path to config.py
            buildargs: Original build arguments
            
        Returns:
            Resolved build arguments (original merged with resolved config)
        """
        try:
            # Dynamically import config module
            spec = importlib.util.spec_from_file_location("env_config", config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            # Look for standard resolve_buildargs function
            if hasattr(config_module, "resolve_buildargs"):
                resolve_func = getattr(config_module, "resolve_buildargs")
                logger.info(f"Found resolve_buildargs in {config_path}")
                
                resolved = resolve_func(buildargs)
                logger.info(f"Resolved build args: {resolved}")
                return resolved
            else:
                logger.debug(f"No resolve_buildargs function in {config_path}")
                return buildargs
                
        except Exception as e:
            logger.warning(f"Failed to resolve build args: {e}")
            return buildargs
    
    def push_image(self, image_tag: str, registry: Optional[str] = None) -> None:
        """
        Push image to registry
        
        Args:
            image_tag: Image tag to push
            registry: Registry URL (optional)
        """
        try:
            if registry:
                full_tag = f"{registry}/{image_tag}"
                logger.info(f"Tagging image {image_tag} as {full_tag}")
                image = self.client.images.get(image_tag)
                image.tag(full_tag)
                push_tag = full_tag
            else:
                push_tag = image_tag
            
            logger.info(f"Pushing image {push_tag}")
            
            for line in self.client.images.push(push_tag, stream=True, decode=True):
                if "status" in line:
                    logger.debug(f"{line['status']}")
                elif "error" in line:
                    raise ImageBuildError(f"Push failed: {line['error']}")
            
            logger.info(f"Successfully pushed {push_tag}")
            
        except docker.errors.APIError as e:
            raise ImageBuildError(f"Failed to push image: {e}")
        except Exception as e:
            raise ImageBuildError(f"Error pushing image: {e}")
    
    def pull_image(self, image_tag: str) -> str:
        """
        Pull image from registry
        
        Args:
            image_tag: Image tag to pull
            
        Returns:
            Image ID
        """
        try:
            logger.info(f"Pulling image {image_tag}")
            
            image = self.client.images.pull(image_tag)
            
            logger.info(f"Successfully pulled {image_tag} ({image.short_id})")
            return image.id
            
        except docker.errors.APIError as e:
            raise ImageBuildError(f"Failed to pull image: {e}")
        except Exception as e:
            raise ImageBuildError(f"Error pulling image: {e}")
    
    def image_exists(self, image_tag: str) -> bool:
        """
        Check if image exists locally
        
        Args:
            image_tag: Image tag to check
            
        Returns:
            True if image exists
        """
        try:
            self.client.images.get(image_tag)
            return True
        except docker.errors.ImageNotFound:
            return False
        except Exception:
            return False
    
    def remove_image(self, image_tag: str, force: bool = False) -> None:
        """
        Remove image
        
        Args:
            image_tag: Image tag to remove
            force: Force removal
        """
        try:
            logger.info(f"Removing image {image_tag}")
            self.client.images.remove(image_tag, force=force)
            logger.info(f"Image {image_tag} removed")
        except docker.errors.ImageNotFound:
            logger.warning(f"Image {image_tag} not found")
        except Exception as e:
            logger.error(f"Failed to remove image: {e}")