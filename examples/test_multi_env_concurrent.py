"""
Multi-Environment Concurrent Test
Tests multiple environments with different instance counts running tasks concurrently
"""

import rayfine_env as rf_env
import asyncio
import time
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)


async def main():
    print("\n" + "=" * 80)
    print("Multi-Environment Concurrent Execution Test")
    print("=" * 80)
    
    # Check API key
    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        sys.exit(1)
    
    total_start = time.time()
    
    # Build images
    print("\n1. Building Docker images...")
    build_start = time.time()
    
    affine_image = rf_env.build_image_from_env(
        env_path="environments/affine",
        image_tag="affine:latest",
        nocache=False,
        quiet=True
    )
    print(f"   ✓ Affine image built")
    
    agentgym_image = rf_env.build_image_from_env(
        env_path="environments/agentgym",
        image_tag="agentgym:webshop",
        nocache=False,
        quiet=True,
        buildargs={"ENV_NAME": "webshop"}
    )
    print(f"   ✓ AgentGym webshop image built")
    
    build_time = time.time() - build_start
    print(f"   Total build time: {build_time:.2f}s")
    
    # Deploy instances
    print("\n2. Deploying instances...")
    deploy_start = time.time()
    
    print("   Deploying affine with 3 instances...")
    env_affine = rf_env.load_env(
        image=affine_image,
        mode="local",
        replicas=3,
        load_balance="random",
        base_port=8000,
        env_vars={"CHUTES_API_KEY": api_key}
    )
    print(f"   ✓ Affine: {env_affine}")
    
    print("   Deploying agentgym:webshop with 2 instances...")
    env_agentgym = rf_env.load_env(
        image=agentgym_image,
        mode="local",
        replicas=2,
        load_balance="round_robin",
        base_port=9000,
        env_vars={"CHUTES_API_KEY": api_key}
    )
    print(f"   ✓ AgentGym: {env_agentgym}")
    
    deploy_time = time.time() - deploy_start
    print(f"   Total deployment time: {deploy_time:.2f}s")
    
    try:
        # Show pool statistics
        print("\n3. Instance pool statistics:")
        
        affine_stats = env_affine.get_stats()
        print(f"\n   Affine pool:")
        print(f"     Total instances: {affine_stats['total_instances']}")
        print(f"     Healthy instances: {affine_stats['healthy_instances']}")
        for inst in affine_stats['instances']:
            print(f"       - {inst['host']}:{inst['port']}")
        
        agentgym_stats = env_agentgym.get_stats()
        print(f"\n   AgentGym pool:")
        print(f"     Total instances: {agentgym_stats['total_instances']}")
        print(f"     Healthy instances: {agentgym_stats['healthy_instances']}")
        for inst in agentgym_stats['instances']:
            print(f"       - {inst['host']}:{inst['port']}")
        
        # Run concurrent tasks
        print("\n4. Running concurrent tasks...")
        print("   Affine: 5x abd + 5x ded + 5x sat = 15 tasks")
        print("   AgentGym: 5x webshop tasks")
        print("   Total: 20 concurrent tasks across 5 instances")
        
        exec_start = time.time()
        
        # Create task lists
        tasks = []
        task_labels = []
        
        # Affine tasks (15 total: 5 abd + 5 ded + 5 sat)
        for i in range(5):
            task = env_affine.evaluate(
                task_type="abd",
                model="deepseek-ai/DeepSeek-V3",
                base_url="https://llm.chutes.ai/v1",
                num_samples=1,
                timeout=60
            )
            tasks.append(task)
            task_labels.append(f"affine-abd-{i+1}")
        
        for i in range(5):
            task = env_affine.evaluate(
                task_type="ded",
                model="deepseek-ai/DeepSeek-V3",
                base_url="https://llm.chutes.ai/v1",
                num_samples=1,
                timeout=60
            )
            tasks.append(task)
            task_labels.append(f"affine-ded-{i+1}")
        
        for i in range(5):
            task = env_affine.evaluate(
                task_type="sat",
                model="deepseek-ai/DeepSeek-V3",
                base_url="https://llm.chutes.ai/v1",
                num_samples=1,
                timeout=60
            )
            tasks.append(task)
            task_labels.append(f"affine-sat-{i+1}")
        
        # AgentGym webshop tasks (5 total)
        for i in range(5):
            task = env_agentgym.evaluate(
                model="deepseek-ai/DeepSeek-V3",
                base_url="https://llm.chutes.ai/v1",
                temperature=0.7,
                ids=[0],
                max_round=10,
                timeout=200
            )
            tasks.append(task)
            task_labels.append(f"agentgym-webshop-{i+1}")
        
        # Execute all tasks concurrently
        print(f"\n   Starting {len(tasks)} concurrent tasks...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        exec_time = time.time() - exec_start
        print(f"   ✓ All tasks completed in {exec_time:.2f}s")
        
        # Analyze results
        print("\n5. Results analysis:")
        
        affine_success = 0
        affine_failed = 0
        agentgym_success = 0
        agentgym_failed = 0
        
        for i, (result, label) in enumerate(zip(results, task_labels)):
            if isinstance(result, Exception):
                print(f"   ❌ {label}: {type(result).__name__}")
                if label.startswith("affine"):
                    affine_failed += 1
                else:
                    agentgym_failed += 1
            else:
                if label.startswith("affine"):
                    affine_success += 1
                    success_rate = result.get('success_rate', 0) * 100
                    print(f"   ✓ {label}: score={result.get('total_score', 0)}, success={success_rate:.0f}%")
                else:
                    agentgym_success += 1
                    print(f"   ✓ {label}: score={result.get('total_score', 0)}, success={success_rate:.0f}%")
        
        print(f"\n   Summary:")
        print(f"     Affine: {affine_success}/{affine_success+affine_failed} successful")
        print(f"     AgentGym: {agentgym_success}/{agentgym_success+agentgym_failed} successful")
        print(f"     Overall: {affine_success+agentgym_success}/{len(tasks)} successful")
        
        # Show load distribution
        print("\n6. Load distribution after concurrent execution:")
        
        affine_stats = env_affine.get_stats()
        print(f"\n   Affine pool (15 tasks across 3 instances):")
        print(f"     Total requests: {affine_stats['total_requests']}")
        for inst in affine_stats['instances']:
            pct = (inst['requests'] / affine_stats['total_requests'] * 100) if affine_stats['total_requests'] > 0 else 0
            print(f"       {inst['host']}:{inst['port']}: {inst['requests']} requests ({pct:.1f}%)")
        
        agentgym_stats = env_agentgym.get_stats()
        print(f"\n   AgentGym pool (5 tasks across 2 instances):")
        print(f"     Total requests: {agentgym_stats['total_requests']}")
        for inst in agentgym_stats['instances']:
            pct = (inst['requests'] / agentgym_stats['total_requests'] * 100) if agentgym_stats['total_requests'] > 0 else 0
            print(f"       {inst['host']}:{inst['port']}: {inst['requests']} requests ({pct:.1f}%)")
        
    except Exception as e:
        print(f"\n   ❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\n7. Cleaning up all environments...")
        cleanup_start = time.time()
        
        await env_affine.cleanup()
        print("   ✓ Affine instances cleaned up")
        
        await env_agentgym.cleanup()
        print("   ✓ AgentGym instances cleaned up")
        
        cleanup_time = time.time() - cleanup_start
        print(f"   Cleanup time: {cleanup_time:.2f}s")
    
    total_time = time.time() - total_start
    
    print("\n" + "=" * 80)
    print("Performance Summary")
    print("=" * 80)
    print(f"  Image build:    {build_time:>8.2f}s")
    print(f"  Deployment:     {deploy_time:>8.2f}s (5 instances total)")
    print(f"  Execution:      {exec_time:>8.2f}s (20 concurrent tasks)")
    print(f"  Cleanup:        {cleanup_time:>8.2f}s")
    print(f"  {'─' * 30}")
    print(f"  Total time:     {total_time:>8.2f}s")
    print("=" * 80)
    print(f"\n✅ Multi-environment concurrent test completed!")
    print(f"   Average throughput: {len(tasks)/exec_time:.2f} tasks/second")
    print(f"   Parallelization speedup: ~{len(tasks)/exec_time:.1f}x\n")


if __name__ == "__main__":
    asyncio.run(main())