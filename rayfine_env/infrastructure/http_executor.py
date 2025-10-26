"""HTTP-based remote execution"""

import httpx
from typing import Any, Optional

from ..utils.exceptions import ExecutionError
from ..utils.logger import logger
from .env_detector import EnvType


class HTTPExecutor:
    """Unified HTTP executor for both environment types"""
    
    def __init__(
        self,
        base_url: str,
        env_type: str,
        timeout: int = 600
    ):
        """
        Args:
            base_url: Container base URL (e.g., http://localhost:8000)
            env_type: EnvType.FUNCTION_BASED or EnvType.HTTP_BASED
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.env_type = env_type
        # Use synchronous client to avoid event loop issues
        self.client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20
            )
        )
        logger.debug(f"HTTPExecutor initialized: {base_url} (type: {env_type})")
    
    def call_method(
        self,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Call method via HTTP
        
        Routes:
        - function_based: POST /call with {"method": "...", "args": [...], "kwargs": {...}}
        - http_based: POST /{method_name} with direct kwargs
        """
        try:
            if self.env_type == EnvType.FUNCTION_BASED:
                # Generic endpoint for function-based
                logger.debug(f"Calling function-based method: {method_name}")
                response = self.client.post(
                    f"{self.base_url}/call",
                    json={
                        "method": method_name,
                        "args": list(args),
                        "kwargs": kwargs
                    }
                )
            else:  # HTTP_BASED
                # Direct endpoint for http-based
                logger.debug(f"Calling http-based endpoint: /{method_name}")
                response = self.client.post(
                    f"{self.base_url}/{method_name}",
                    json=kwargs
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response
            if isinstance(data, dict):
                if "status" in data:
                    # MethodResponse format (function_based)
                    if data["status"] != "success":
                        raise ExecutionError(f"Remote execution failed: {data}")
                    return data.get("result")
                else:
                    # Direct result (http_based)
                    return data
            else:
                return data
                
        except httpx.HTTPStatusError as e:
            raise ExecutionError(
                f"HTTP {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            raise ExecutionError(f"Failed to call method '{method_name}': {e}")
    
    def list_methods(self) -> list:
        """List available methods"""
        try:
            if self.env_type == EnvType.FUNCTION_BASED:
                response = self.client.get(f"{self.base_url}/methods")
                data = response.json()
                return data.get("methods", [])
            else:
                # For http_based, inspect OpenAPI schema
                response = self.client.get(f"{self.base_url}/openapi.json")
                schema = response.json()
                return list(schema.get("paths", {}).keys())
        except Exception as e:
            logger.warning(f"Failed to list methods: {e}")
            return []
    
    def health_check(self) -> bool:
        """Check server health"""
        try:
            response = self.client.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    def close(self):
        """Close HTTP client"""
        self.client.close()