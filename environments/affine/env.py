"""Affine Environment Actor"""

import os
import time
import httpx
import openai
import sys

# Add /app to path to import local modules
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from sat import SATTask

class Actor:
    """Multi-task evaluation actor"""
    
    # Task registry - map task_type to task class
    TASKS = {
        "sat": SATTask,
        # Future: "graph": GraphTask, "crypto": CryptoTask, ...
    }
    
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")
        if not self.api_key:
            raise ValueError("CHUTES_API_KEY not set")
    
    async def _llm_chat(self, prompt, model, base_url, timeout, temperature):
        """Call LLM API"""
        # Unset SSL_CERT_FILE to avoid certificate path issues in container
        # Let httpx/certifi use default certificate bundle
        import os
        os.environ.pop('SSL_CERT_FILE', None)
        os.environ.pop('REQUESTS_CA_BUNDLE', None)
        
        client = openai.AsyncOpenAI(
            base_url=base_url.rstrip('/'),
            api_key=self.api_key,
            timeout=httpx.Timeout(timeout),
            max_retries=0
        )
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=False
        )
        
        return response.choices[0].message.content.strip()
    
    async def evaluate(
        self,
        task_type="sat",
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        num_samples=1,
        timeout=600,
        temperature=0.7
    ):
        """Run evaluation"""
        # Get task class from registry
        task_cls = self.TASKS.get(task_type)
        if not task_cls:
            raise ValueError(f"Unknown task: {task_type}. Available: {list(self.TASKS.keys())}")
        
        start = time.time()
        details = []
        total_score = 0.0
        
        for i in range(num_samples):
            # Generate task
            prompt, sol, cls = task_cls.generate()
            
            # Call LLM
            try:
                resp = await self._llm_chat(prompt, model, base_url, timeout, temperature)
                error = None
            except Exception as e:
                import traceback
                resp = None
                error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            
            # Evaluate
            score = 0.0
            if resp:
                score = task_cls.evaluate(resp, cls)
            
            total_score += score
            details.append({
                "id": i,
                "reward": score,
                "success": score > 0,
                "experiences": {"challenge": prompt, "llm_response": resp},
                **({} if not error else {"error": error, "error_type": "llm_failure"})
            })
        
        return {
            "task_name": f"affine:{task_type}",
            "total_score": total_score,
            "success_rate": sum(1 for d in details if d["success"]) / num_samples,
            "num_evaluated": num_samples,
            "time_taken": time.time() - start,
            "details": details
        }
        
        
def evaluate(**args):
    """
    Wrapper function to expose Actor.evaluate() to external callers.
    
    All container images must include /app/env.py as the entry point.
    The env.py file can define arbitrary functions that will be exposed through the SDK.
    This is just one example - you can define any functions you need.
    """
    pass