"""Example: Evaluate AgentGym environment (webshop)"""

import asyncio
import os
import sys
import rayfine_env as rf_env
from dotenv import load_dotenv
load_dotenv(override=True)

async def main():
    # Setup environment with build args
    image_id = rf_env.build_image_from_env(
        env_path="environments/agentgym",
        image_tag="agentgym:webshop",
        buildargs={
            "ENV_NAME": "webshop"
        }
    )

    env = rf_env.load_env(
        image=image_id,
        mode="local"
    )

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        env.cleanup()
        sys.exit(1)

    env.setup(CHUTES_API_KEY=api_key)
    print("   ✓ Environment setup complete (Ray Actor created)")
    
    # Run evaluation
    print("\nRunning evaluation...")
    result = await env.evaluate(
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        temperature=0.7,
        ids=[0],
        max_round=10,
        timeout=2400
    )
    
    print(f"\nResults:")
    print(f"Task: {result['task_name']}")
    print(f"Total Score: {result['total_score']:.3f}")
    print(f"Success Rate: {result['success_rate']:.3f}")
    print(f"Evaluated: {result['num_evaluated']} samples")
    print(f"Time: {result['time_taken']:.1f}s")
    
    # Show details
    print(f"\nDetails:")
    for detail in result['details']:
        if 'error' in detail:
            print(f"  Sample {detail['id']}: ERROR - {detail['error']}")
        else:
            print(f"  Sample {detail['id']}: reward={detail['reward']:.3f}, success={detail['success']}")

if __name__ == "__main__":
    asyncio.run(main())