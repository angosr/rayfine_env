# Rayfine-Env

Container-based environment execution framework with Ray-based distributed computing.

Define environments once, execute anywhere with Docker + Ray.

## Features

- **Simple Environment Definition**: Only requires `env.py` file
- **Container Isolation**: All environments run in isolated Docker containers
- **Ray Integration**: Distributed computing with remote Actor execution
- **Dynamic Method Dispatch**: Automatic method exposure via `__getattr__`
- **Multi-Environment Support**: Run multiple environments concurrently
- **Backend Abstraction**: Local (Docker+Ray) and Remote (API) modes
- **Clean Separation**: Environment variables injected at setup, not container start

## Quick Start

### 1. Define Environment

Create an environment directory with `env.py`:

```python
# environments/affine/env.py
import os

class Actor:
    """Optional Actor class for structured environments"""
    
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")
    
    async def evaluate(self, task_type="sat", num_samples=1, **kwargs):
        # Your implementation
        return {"task_name": task_type, "total_score": 1.0}

# Or define module-level functions (simpler approach)
async def evaluate(task_type="sat", num_samples=1, **kwargs):
    api_key = os.getenv("CHUTES_API_KEY")
    # Your implementation
    return {"task_name": task_type, "total_score": 1.0}
```

Optional `Dockerfile` (auto-generated if not provided):

```dockerfile
# environments/affine/Dockerfile
FROM rayproject/ray:latest
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 10001
CMD ["ray", "start", "--head", "--port=6379", "--dashboard-host=0.0.0.0", "--block"]
```

### 2. Build Image

```python
from rayfine_env import build_image_from_env

# Build Docker image from environment directory
image_id = build_image_from_env(
    env_path="environments/affine",
    image_tag="affine:latest"
)
```

### 3. Load and Execute

```python
from rayfine_env import load_env

# Load environment (starts container)
env = load_env(image="affine:latest", mode="local")

# Setup with environment variables
env.setup(CHUTES_API_KEY="your-api-key")

# Execute methods dynamically
result = env.evaluate(task_type="sat", num_samples=5)

# Cleanup
env.cleanup()
```

### 4. Context Manager (Auto-cleanup)

```python
with load_env(image="affine:latest") as env:
    env.setup(CHUTES_API_KEY="xxx")
    result = env.evaluate(task_type="sat", num_samples=5)
# Container automatically cleaned up
```

## API Reference

### `build_image_from_env()`

Build Docker image from environment directory.

```python
build_image_from_env(
    env_path: str,                          # Path to environment directory
    image_tag: str,                         # Image tag (e.g., "affine:latest")
    base_image: str = "rayproject/ray:latest",  # Base image
    nocache: bool = False,                  # Don't use build cache
    quiet: bool = False                     # Suppress build output
) -> str  # Returns image ID
```

**Requirements:**
- `env_path` must contain `env.py` file
- Optional: `Dockerfile`, `requirements.txt`, other Python files

### `load_env()`

Load environment from pre-built Docker image.

```python
load_env(
    image: str,                  # Docker image name
    mode: str = "local",         # "local" or "remote"
    container_name: str = None,  # Optional container name
    ray_port: int = 10001,       # Ray client port
    **kwargs                     # Additional backend options
) -> EnvironmentWrapper
```

### EnvironmentWrapper Methods

```python
env.setup(**env_vars)           # Initialize with environment variables
env.cleanup()                   # Stop container and cleanup
env.list_methods()              # List available methods
env.is_ready()                  # Check if ready for execution
env.<method_name>(**kwargs)     # Call any method from env.py
```

### Utility Functions

```python
list_active_environments()      # List all active environment IDs
cleanup_all_environments()      # Cleanup all environments (auto on exit)
get_environment(env_id)         # Get environment by ID
```

## Architecture

```
rayfine_env/
├── __init__.py          # Public API exports
├── __version__.py       # Version info
├── api.py               # Main API functions
├── utils/               # Utilities layer
│   ├── exceptions.py    # Custom exceptions
│   ├── logger.py        # Centralized logging
│   └── config.py        # Configuration
├── infrastructure/      # Infrastructure layer
│   ├── docker_manager.py   # Docker container management
│   ├── ray_executor.py     # Ray cluster connection
│   └── image_builder.py    # Image building
├── backends/            # Backend layer
│   ├── base.py          # Abstract backend interface
│   ├── local.py         # Local Docker+Ray backend
│   └── remote.py        # Remote API backend (stub)
└── core/                # Core layer
    ├── registry.py      # Environment registry
    └── wrapper.py       # Environment wrapper
```

## How It Works

### Execution Flow

1. **Build Phase** (once):
   - Parse environment directory
   - Generate Dockerfile if needed
   - Build Docker image with Ray

2. **Load Phase**:
   - Start Docker container
   - Wait for Ray cluster to be ready
   - Return EnvironmentWrapper

3. **Setup Phase**:
   - Connect to Ray cluster
   - Create Ray Actor with environment variables
   - Actor loads `/app/env.py` module

4. **Execution Phase**:
   - Method calls → Ray Actor → User's env.py
   - Results returned to caller

5. **Cleanup Phase**:
   - Disconnect Ray
   - Stop and remove container

### Multi-Environment Support

Each environment gets:
- Independent Docker container
- Independent Ray cluster
- Isolated execution context

```python
# Run multiple environments concurrently
env1 = load_env(image="affine:latest")
env2 = load_env(image="custom:v1")

env1.setup(API_KEY="key1")
env2.setup(API_KEY="key2")

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
- Ray 2.9+ (auto-installed)

## Installation

```bash
# Install from source
pip install -e .

# Or install from PyPI (when published)
pip install rayfine-env
```

## Backend Modes

### Local Mode (Docker + Ray)
- Free and open-source
- Full control over containers
- Good for development and testing

### Remote Mode (API) - Coming Soon
- Managed service
- No local Docker required
- Pay-per-use pricing

## Examples

See `example.py` and `test/example.py` for complete examples.

### Build Example

```bash
$ python example.py
```

### Runtime Example

```bash
$ python test/example.py
```

## Environment Definition Guide

### Minimal Example (Function-based)

```python
# env.py
def hello(name="World"):
    return f"Hello, {name}!"
```

### Actor-based Example

```python
# env.py
import os

class Actor:
    def __init__(self):
        self.config = os.getenv("MY_CONFIG")
    
    def process(self, data):
        return {"processed": data, "config": self.config}
```

### Mixed Example

```python
# env.py
class Actor:
    def method_a(self):
        return "from Actor"

def method_b():
    return "from module"

# Both methods are available:
# env.method_a()  → calls Actor().method_a()
# env.method_b()  → calls method_b()
```

## License

MIT