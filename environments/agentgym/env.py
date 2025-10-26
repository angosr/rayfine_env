#!/usr/bin/env python3

import os
import sys
import importlib
from loguru import logger
import time
import asyncio
import httpx
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from functools import partial

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


ENV_NAME = os.environ.get("ENV_NAME")
TOOL_NAME = os.environ.get("TOOL_NAME", "")

class EvaluatorRequest(BaseModel):
    model: str
    base_url: str = "https://llm.chutes.ai/v1"
    max_tokens: int = None
    temperature: float = 0.7
    top_p: float = 1.0
    ids: Optional[List[int]] = None
    max_round: int = 10
    env_server_base: Optional[str] = "http://localhost:8000"
    data_len: int = 200
    timeout: int = 2400


class EvaluatorResponse(BaseModel):
    task_name: str
    total_score: float
    success_rate: float
    num_evaluated: int
    time_taken: float
    details: List[Dict[str, Any]]


def inject_health_endpoint(app: FastAPI):
    """Inject a health check endpoint into the existing FastAPI app."""

    for route in app.routes:
        if hasattr(route, 'path') and route.path == '/health':
            logger.info("Health endpoint already exists, skipping injection")
            return

    @app.get("/health")
    async def health_check():
        return "ok"

    logger.info("Health endpoint injected successfully")


async def validate_api_key(api_key: str, base_url: str) -> bool:
    """Validate the API key by making a test request to the API."""
    if not api_key:
        return False
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            return response.status_code >= 200 and response.status_code < 300
    except Exception as e:
        logger.error(f"API key validation failed: {e}")
        return False


def inject_evaluator_endpoint(app: FastAPI):
    """Inject an evaluator endpoint into the existing FastAPI app."""
    
    for route in app.routes:
        if hasattr(route, 'path') and route.path == '/evaluator':
            logger.info("Evaluator endpoint already exists, skipping injection")
            return

    @app.post("/evaluator", response_model=EvaluatorResponse)
    async def evaluate_model(request: EvaluatorRequest):
        """
        Evaluate a model on AgentGym tasks.
        
        This endpoint allows evaluating language models on various AgentGym tasks
        by providing model configuration and task parameters.
        """
        try:
            from agentenv.controller import APIAgent, Evaluator

            # Import task classes dynamically
            task_modules = {
                "webshop": "WebshopTask",
                "alfworld": "AlfWorldTask",
                "babyai": "BabyAITask",
                "sciworld": "SciworldTask",
                "textcraft": "TextCraftTask",
                "webarena": "WebarenaTask",
                "sqlgym": "SqlGymTask",
                "maze": "MazeTask",
                "wordle": "WordleTask",
                "weather": "WeatherTask",
                "todo": "TodoTask",
                "movie": "MovieTask",
                "sheet": "SheetTask",
                "academia": "AcademiaTask",
                "searchqa": "SearchQATask",
            }
            if ENV_NAME == "tool" or ENV_NAME == "lmrlgym":
                class_name = task_modules[TOOL_NAME]
            else:
                class_name = task_modules[ENV_NAME]
            module = importlib.import_module("agentenv.envs")
            task_class = getattr(module, class_name)

            env_server_base = request.env_server_base
            if not env_server_base:
                env_server_base = f"http://localhost:8000"
            if ENV_NAME == "lmrlgym":
                env_server_base += f"/{TOOL_NAME}"
            env_args = {
                "env_server_base": env_server_base,
                "data_len": request.data_len,
                "timeout": request.timeout,
            }

            api_key = os.environ.get("CHUTES_API_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail="CHUTES_API_KEY environment variable is not set"
                )

            is_valid = await validate_api_key(api_key, request.base_url)
            if not is_valid:
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid API key for {request.base_url}. Please check your CHUTES_API_KEY environment variable."
                )

            logger.info(f"API key validated successfully for {request.base_url}")
            
            agent = APIAgent(
                api_key=api_key,
                base_url=request.base_url,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
            )
            
            if request.ids:
                data_idxs = request.ids
            else:
                data_idxs = list(range(min(request.data_len, 200)))

            loop = asyncio.get_event_loop()
            def create_evaluator():
                """Create evaluator in thread to avoid blocking"""
                task_instance = task_class(client_args=env_args, n_clients=1)
                return Evaluator(agent, [task_instance])
            evaluator = await loop.run_in_executor(None, create_evaluator)
            logger.info("Evaluator created successfully")

            total_score = 0.0
            total_success = 0.0
            details = []
            start_time = time.time()
            logger.info(f"data_idxs: {data_idxs}")
            for data_idx in data_idxs:
                try:
                    exps = await loop.run_in_executor(
                        None,
                        partial(
                            evaluator.eval,
                            max_rounds=request.max_round,
                            idxs=[data_idx]
                        )
                    )
                    
                    reward = exps.score
                    success = exps.success

                    total_score += reward
                    total_success += success
                    
                    details.append({
                        "id": data_idx,
                        "reward": reward,
                        "success": success,
                        "experiences": exps.experiences
                    })
                except Exception as e:
                    logger.error(f"Error evaluating index {data_idx}: {e}")
                    traceback.print_exc()
                    details.append({
                        "id": data_idx,
                        "reward": 0.0,
                        "success": False,
                        "error": str(e)
                    })
            
            # Calculate metrics
            num_evaluated = len(details)
            time_taken = time.time() - start_time
            
            if num_evaluated > 0:
                avg_score = total_score / num_evaluated
                success_rate = total_success / num_evaluated
            else:
                avg_score = 0.0
                success_rate = 0.0
            
            # Return response
            env_name = os.environ.get("ENV_NAME")
            return EvaluatorResponse(
                task_name=env_name,
                total_score=avg_score,
                success_rate=success_rate,
                num_evaluated=num_evaluated,
                time_taken=time_taken,
                details=details
            )
            
        except ImportError as e:
            logger.error(f"Import error: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to import required modules: {e}")
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(tb_str)
            raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}, {tb_str}")
    
    logger.info("Evaluator endpoint injected successfully")


def create_app():
    logger.info(f"Loading {ENV_NAME} environment server")
    if ENV_NAME == "tool":
        module_name = f"agentenv_{TOOL_NAME}.{TOOL_NAME}_server"
    else:
        module_name = f"agentenv_{ENV_NAME}.server"
    try:
        logger.info(f"Importing module: {module_name}")
        os.chdir(f"/app/AgentGym/agentenv-{ENV_NAME}")
        if ENV_NAME == "lmrlgym":
            sys.path.insert(0, "/app/AgentGym/agentenv-lmrlgym/lmrlgym")
        if ENV_NAME == "sqlgym":
            sys.path.insert(0, "/app/AgentGym/agentenv-sqlgym")
            os.environ["AGENTENV_SQLGYM_BIRD_PATH"] = "/app/AgentGym/agentenv-sqlgym/bird/"
        if ENV_NAME == "tool":
            sys.path.insert(0, "/app/AgentGym/agentenv-tool/Toolusage/toolusage")
            sys.path.insert(0, "/app/AgentGym/agentenv-tool")
            os.environ["PROJECT_PATH"] = "/app/AgentGym/agentenv-tool/Toolusage"

        server_module = importlib.import_module(module_name)
        app = server_module.app
        logger.info(f"Successfully loaded {ENV_NAME} environment app")
        
        inject_health_endpoint(app)
        inject_evaluator_endpoint(app)
        
        return app
    except Exception as e:
        logger.error(f"Unexpected error loading environment: {e}")
        import traceback
        traceback.print_exc()
        

app = create_app()

@app.on_event("startup")
async def startup_event():
    env_name = os.environ.get("ENV_NAME", "unknown")
    logger.info(f"Environment server ready for: {env_name}")