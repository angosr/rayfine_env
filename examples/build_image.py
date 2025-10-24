"""
Example: Build Docker image from environment definition

This example shows how to build a Docker image from an environment directory.
The environment must contain an env.py file.
"""

import rayfine_env as rf_env
from dotenv import load_dotenv

load_dotenv(override=True)


def main():
    print("=" * 60)
    print("Building Docker Image from Environment")
    print("=" * 60)
    
    # Build image from environment directory
    print("\nBuilding image 'affine:latest' from 'environments/affine'...")
    
    try:
        image_id = rf_env.build_image_from_env(
            env_path="environments/affine",
            image_tag="affine:latest",
            nocache=False,
            quiet=False
        )
        
        print(f"\n✓ Image built successfully!")
        print(f"  Image ID: {image_id[:20]}...")
        print(f"  Image tag: affine:latest")
        print(f"\nYou can now load this environment with:")
        print(f"  env = rf_env.load_env(image='affine:latest')")
        
    except Exception as e:
        print(f"\n❌ Failed to build image: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()