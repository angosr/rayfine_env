# Rayfine-Env

Container-based environment execution framework with HTTP-based communication.

Define environments once, execute anywhere with Docker + HTTP.

## Features

- **Simple Environment Definition**: Only requires `env.py` file
- **Container Isolation**: All environments run in isolated Docker containers
- **HTTP Communication**: Language-agnostic REST API for cross-version compatibility
- **Two Environment Types**: 
  - Function-based (auto-injected HTTP server)
  - HTTP-based (existing FastAPI servers)
- **Dynamic Method Dispatch**: Automatic method exposure via `__getattr__`
- **Multi-Environment Support**: Run multiple environments concurrently
- **Backend Abstraction**: Local (Docker+HTTP) and Remote (API) modes
- **Zero Burden**: Environment developers only write business logic

## Quick Start

### 1. Define Environment

Create an environment directory with `env.py`:

```python
# environments/affine/env.py
import os

class Actor:
    """Actor class for structured environments"""
    
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")
        if not self.api_key:
            raise ValueError("CHUTES_API_KEY not set")
    
    async def evaluate(self, task_type="sat", num_samples=1, **kwargs):
        # Your implementation
        return {
            "task_name": task_type, 
            "total_score": 1.0,
            "samples": num_samples
        }

# Or define module-level functions (simpler approach)
async def evaluate(task_type="sat", num_samples=1, **kwargs):
    api_key = os.getenv("CHUTES_API_KEY")
    # Your implementation
    return {"task_name": task_type, "total_score": 1.0}
```

Optional [`Dockerfile`](environments/affine/Dockerfile) (base image for dependencies):

```dockerfile
# environments/affine/Dockerfile
FROM rayproject/ray:2.40.0-py312
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
```

### 2. Build Image

```python
import rayfine_env as rf_env

# Build Docker image from environment directory
image_id = rf_env.build_image_from_env(
    env_path="environments/affine",
    image_tag="affine:latest"
)
# HTTP server is automatically injected for function-based environments
```

### 3. Load and Execute

```python
import rayfine_env as rf_env

# Load environment (starts container with env vars)
env = rf_env.load_env(
    image="affine:latest",
    mode="local",
    env_vars={"CHUTES_API_KEY": "your-api-key"}
)

# Execute methods dynamically (no setup() needed)
result = env.evaluate(task_type="sat", num_samples=5)

# Cleanup
env.cleanup()
```

### 4. Context Manager (Auto-cleanup)

```python
with rf_env.load_env(
    image="affine:latest",
    env_vars={"CHUTES_API_KEY": "xxx"}
) as env:
    result = env.evaluate(task_type="sat", num_samples=5)
# Container automatically cleaned up
```

## API Reference

### [`build_image_from_env()`](rayfine_env/api.py)

Build Docker image from environment directory.

```python
rf_env.build_image_from_env(
    env_path: str,                          # Path to environment directory
    image_tag: str,                         # Image tag (e.g., "affine:latest")
    nocache: bool = False,                  # Don't use build cache
    quiet: bool = False,                    # Suppress build output
    buildargs: Dict[str, str] = None        # Docker build arguments
) -> str  # Returns image tag
```

**Requirements:**
- `env_path` must contain `env.py` file
- Optional: `Dockerfile`, `requirements.txt`, other Python files

**Behavior:**
- Detects environment type (function-based or http-based)
- For function-based: Builds base image, then injects HTTP server (two-stage build)
- For http-based: Uses existing Dockerfile as-is

### [`load_env()`](rayfine_env/api.py)

Load environment from pre-built Docker image.

```python
rf_env.load_env(
    image: str,                     # Docker image name
    mode: str = "local",            # "local" or "remote"
    container_name: str = None,     # Optional container name
    http_port: int = 8000,          # HTTP server port
    env_vars: Dict[str, str] = None,# Environment variables
    env_type: str = None,           # Override type detection
    **kwargs                        # Additional backend options
) -> EnvironmentWrapper
```

**Important:** Environment variables should be passed via `env_vars` parameter, not `setup()`.

### EnvironmentWrapper Methods

```python
env.cleanup()                   # Stop container and cleanup
env.list_methods()              # List available methods
env.is_ready()                  # Check if ready for execution
env.<method_name>(**kwargs)     # Call any method from env.py
```

### Utility Functions

```python
rf_env.list_active_environments()      # List all active environment IDs
rf_env.cleanup_all_environments()      # Cleanup all environments (auto on exit)
rf_env.get_environment(env_id)         # Get environment by ID
```

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Application                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  import rayfine_env as rf_env                          │ │
│  │  env = rf_env.load_env("affine:latest")                │ │
│  │  result = env.evaluate(...)                            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Rayfine-Env Framework                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  API Layer   │  │ Core Layer   │  │  Backend     │      │
│  │  - build_*   │→ │ - Wrapper    │→ │  - Local     │      │
│  │  - load_env  │  │ - Registry   │  │  - Remote    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                           │                   │              │
│  ┌──────────────┐        │                   │              │
│  │Infrastructure│◄───────┘                   │              │
│  │- ImageBuilder│                            │              │
│  │- EnvDetector │                            │              │
│  │- HTTPExecutor│◄───────────────────────────┘              │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ HTTP (port 8000)
┌─────────────────────────────────────────────────────────────┐
│                   Docker Container                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              HTTP Server (Uvicorn)                     │ │
│  │  - GET  /health                                        │ │
│  │  - GET  /methods                                       │ │
│  │  - POST /call  {"method": "evaluate", "args": [...]}   │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              User's env.py                             │ │
│  │  class Actor:                                          │ │
│  │      def __init__(self): ...                           │ │
│  │      async def evaluate(self, ...): ...                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Module Structure

```
rayfine_env/
├── __init__.py              # Public API exports
├── __version__.py           # Version info
├── api.py                   # Main API functions
│
├── utils/                   # Utilities layer
│   ├── exceptions.py        # Custom exceptions
│   ├── logger.py            # Centralized logging
│   └── config.py            # Configuration
│
├── infrastructure/          # Infrastructure layer
│   ├── docker_manager.py    # Docker container management
│   ├── http_executor.py     # HTTP-based remote execution
│   ├── env_detector.py      # Environment type detection
│   └── image_builder.py     # Two-stage image building
│
├── backends/                # Backend layer
│   ├── base.py              # Abstract backend interface
│   ├── local.py             # Local Docker+HTTP backend
│   └── remote.py            # Remote API backend (stub)
│
├── core/                    # Core layer
│   ├── registry.py          # Environment registry
│   └── wrapper.py           # Environment wrapper
│
└── templates/               # Template files
    ├── http_server.py       # Auto-injected HTTP server
    └── http_wrapper.Dockerfile  # Two-stage build Dockerfile
```

## How It Works

### Two-Stage Build Process

For **function-based** environments:

```
Stage 1: Build base image
  └─> User's Dockerfile → affine:latest-base

Stage 2: Inject HTTP server
  └─> FROM affine:latest-base
      COPY http_server.py → /app/_rayfine/server.py
      CMD uvicorn _rayfine.server:app → affine:latest
```

For **http-based** environments (existing FastAPI):
```
Single stage: Use Dockerfile as-is
  └─> User's Dockerfile → agentgym:webshop
      (Already contains FastAPI server)
```

### Execution Flow

1. **Build Phase** (once):
   - Detect environment type ([`EnvDetector`](rayfine_env/infrastructure/env_detector.py))
   - Build base image (if function-based)
   - Inject HTTP server template (if function-based)
   - Tag final image with metadata

2. **Load Phase**:
   - Start Docker container with env vars
   - Wait for HTTP server health check
   - Return [`EnvironmentWrapper`](rayfine_env/core/wrapper.py)

3. **Execution Phase**:
   - Method calls → [`HTTPExecutor`](rayfine_env/infrastructure/http_executor.py) → Container HTTP API
   - Results returned to caller

4. **Cleanup Phase**:
   - Close HTTP client
   - Stop and remove container

### Environment Type Detection

```python
# rayfine_env/infrastructure/env_detector.py

def detect(env_path: str) -> str:
    """
    Returns:
      - EnvType.FUNCTION_BASED: Has Actor class or module functions
      - EnvType.HTTP_BASED: Has FastAPI app in env.py or CMD with uvicorn
    """
```

### HTTP Communication

**Function-based** environment endpoints:
```
POST /call
{
  "method": "evaluate",
  "args": [1, 2, 3],
  "kwargs": {"key": "value"}
}

GET /methods → {"methods": ["evaluate", "process", ...]}
GET /health → "ok"
```

**HTTP-based** environment:
- Direct FastAPI routes (e.g., `POST /evaluator`)
- Framework calls user's existing endpoints

## Environment Types

### Function-Based (Recommended)

**Definition:**
```python
# env.py
class Actor:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
    
    async def evaluate(self, **kwargs):
        return {"result": "success"}
```

**Dockerfile:**
```dockerfile
FROM rayproject/ray:2.40.0-py312
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app/
# No CMD needed - HTTP server auto-injected
```

**Characteristics:**
- Framework auto-injects HTTP server
- Zero HTTP code required
- Lazy Actor initialization (env vars available at runtime)

### HTTP-Based (Advanced)

**Definition:**
```python
# env.py
from fastapi import FastAPI

app = FastAPI()

@app.post("/evaluate")
async def evaluate(request: EvalRequest):
    return {"result": "success"}
```

**Dockerfile:**
```dockerfile
FROM python:3.9
WORKDIR /app
COPY . /app/
RUN pip install fastapi uvicorn
CMD ["uvicorn", "env:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Characteristics:**
- Full control over HTTP server
- Can use existing FastAPI applications
- Suitable for complex services

## Examples

### Basic Function-Based Environment

```bash
python examples/build_image.py    # Build affine:latest
python examples/evaluate.py       # Run evaluation
```

### HTTP-Based Environment

```python
# Manual env_type override for images without metadata
env = rf_env.load_env(
    image="agentgym:webshop",
    env_type="http_based",  # Override detection
    env_vars={"CHUTES_API_KEY": "xxx"}
)
```

## Multi-Environment Support

Each environment gets:
- Independent Docker container
- Independent HTTP server
- Isolated execution context
- Independent environment variables

```python
# Run multiple environments concurrently
env1 = rf_env.load_env(
    image="affine:latest",
    env_vars={"API_KEY": "key1"}
)
env2 = rf_env.load_env(
    image="custom:v1",
    env_vars={"API_KEY": "key2"}
)

# Execute concurrently
result1 = env1.evaluate(...)
result2 = env2.custom_method(...)

# Cleanup
env1.cleanup()
env2.cleanup()
```

## Requirements

- Python 3.8+
- Docker daemon running
- httpx>=0.27.0 (auto-installed)

## Installation

```bash
# Install from source
pip install -e .

# Or install dependencies
pip install -r requirements.txt
```

## Backend Modes

### Local Mode (Docker + HTTP)
- Free and open-source
- Full control over containers
- Good for development and production

### Remote Mode (API) - Coming Soon
- Managed service
- No local Docker required
- Pay-per-use pricing

## Key Design Decisions

### Why HTTP over Ray?

| Aspect | Ray | HTTP |
|--------|-----|------|
| Python version | Must match exactly | Any version |
| Serialization | Ray-specific | Language-agnostic JSON |
| Complexity | Cluster management | Simple REST API |
| Dependencies | Ray SDK required | Standard httpx |
| Debugging | Difficult | Standard HTTP logs |

### Why Two-Stage Build?

- **Clean separation**: Base image (dependencies) + Server layer (framework)
- **Zero burden**: Environment developers don't write HTTP code
- **Maintainability**: HTTP server updates don't require image rebuilds
- **Elegance**: `FROM affine:latest-base` vs concatenating Dockerfiles

## Troubleshooting

### Container startup timeout

```python
# Increase health check timeout (default 60s)
env = rf_env.load_env(image="slow:latest")
# If container takes >60s to start, check:
# 1. Docker logs: docker logs <container_name>
# 2. Image CMD starts HTTP server on port 8000
# 3. /health endpoint is accessible
```

### Environment type detection

```python
# Manually override if detection fails
env = rf_env.load_env(
    image="my:image",
    env_type="http_based"  # or "function_based"
)
```

### Method not found

```python
# List available methods
methods = env.list_methods()
print(methods)
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- Code follows existing patterns
- Tests pass (when available)
- Documentation is updated
