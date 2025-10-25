"""
Example: Load and interact with environment

This example shows how to load an environment from a pre-built Docker image,
set it up with environment variables, and execute methods.
"""

import rayfine_env as rf_env
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)


def main():
    print("\n" + "=" * 60)
    print("Rayfine-Env: Environment Execution Example")
    print("=" * 60)

    # 1. Load environment from pre-built image
    print("\n1. Loading environment from pre-built image 'affine:latest'...")
    
    env = rf_env.load_env(
        image="affine:latest",
        mode="local"
    )
    print("   ✓ Environment loaded (container started)")


    try:
        # 2. Setup environment with API key
        print("\n2. Setting up environment with configuration...")
        api_key = os.getenv("CHUTES_API_KEY")
        if not api_key:
            print("   ❌ CHUTES_API_KEY environment variable not set")
            print("   Please set: export CHUTES_API_KEY='your-key'")
            print("   Or create .env file with: CHUTES_API_KEY=your-key")
            env.cleanup()
            sys.exit(1)

        env.setup(CHUTES_API_KEY=api_key)
        print("   ✓ Environment setup complete (Ray Actor created)")
        
        # 3. List available methods
        print("\n3. Available methods in environment:")
        methods = env.list_methods()
        for method in methods:
            print(f"   - {method}()")
        
        # 4. Run evaluation
        print("\n4. Running evaluation in container...")
        result = env.evaluate(
            task_type="abd",
            model="deepseek-ai/DeepSeek-V3",
            base_url="https://llm.chutes.ai/v1",
            num_samples=2
        )
        
        # 5. Display results
        print(f"\n5. Results:")
        print(f"   Task: {result['task_name']}")
        print(f"   Total score: {result['total_score']}")
        print(f"   Success rate: {result['success_rate'] * 100:.1f}%")
        print(f"   Time taken: {result['time_taken']:.2f}s")
        
        # Show details
        print(f"\n   Sample details:")
        for detail in result['details']:
            print(f"\n   Sample {detail['id']}:")
            print(f"     Success: {detail['success']}")
            print(f"     Reward: {detail['reward']}")
            
            # Show error if any
            if 'error' in detail:
                print(f"     Error type: {detail.get('error_type', 'unknown')}")
                print(f"     Error: {detail['error'][:200]}...")
            
            # Show experiences
            if 'experiences' in detail:
                exp = detail['experiences']
                print(f"     Challenge: {exp['challenge'][:500]}...")
                if exp['llm_response']:
                    print(f"     Response: {exp['llm_response'][:500]}...")
                else:
                    print(f"     Response: None (LLM call failed)")
        
    except Exception as e:
        print(f"\n   ❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 6. Cleanup
        print("\n6. Cleaning up environment...")
        env.cleanup()
        print("   ✓ Environment cleaned up (container stopped)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()