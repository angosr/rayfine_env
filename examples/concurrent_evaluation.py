"""
Example: Concurrent evaluation with async/await

This example demonstrates the power of async HTTP calls by running
multiple evaluations concurrently, which is much faster than sequential execution.
"""

import rayfine_env as rf_env
import os
import sys
import asyncio
import time
from dotenv import load_dotenv

load_dotenv(override=True)


async def run_evaluation(env, task_type: str, num_samples: int):
    """Run a single evaluation task"""
    start = time.time()
    result = await env.evaluate(
        task_type=task_type,
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        num_samples=num_samples
    )
    duration = time.time() - start
    
    print(f"\n✓ {task_type.upper()} completed in {duration:.2f}s")
    print(f"  Score: {result['total_score']}, Success rate: {result['success_rate'] * 100:.1f}%")
    
    return result


async def main():
    print("\n" + "=" * 80)
    print("Rayfine-Env: Concurrent Async Evaluation Example")
    print("=" * 80)

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n❌ CHUTES_API_KEY environment variable not set")
        sys.exit(1)

    # Build image
    image = rf_env.build_image_from_env(
        env_path="environments/affine",
        image_tag="affine:latest",
        nocache=False,
        quiet=True
    )

    print("\n1. Loading environment...")
    env = rf_env.load_env(
        image=image,
        mode="local",
        env_vars={"CHUTES_API_KEY": api_key}
    )
    print("   ✓ Environment loaded")

    try:
        # Show available methods
        print("\n2. Available methods:")
        await env.list_methods(print_info=True)

        # Run multiple evaluations concurrently
        print("\n3. Running multiple evaluations CONCURRENTLY...")
        print("   (This would be much slower if run sequentially)")
        
        start_time = time.time()
        
        # Create multiple concurrent tasks
        tasks = [
            run_evaluation(env, "abd", 2),
            run_evaluation(env, "sat", 2),
            run_evaluation(env, "ded", 2),
        ]
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        print("\n" + "=" * 80)
        print(f"✓ All evaluations completed in {total_time:.2f}s")
        print(f"  Tasks run: {len(tasks)}")
        print(f"  Average time per task: {total_time / len(tasks):.2f}s")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await env.cleanup()
        print("\n✓ Environment cleaned up")


if __name__ == "__main__":
    asyncio.run(main())