"""Piano Hero — Rock Band-style piano learning game.

Connect your keyboard via audio cable and play along!

Usage:
    python main.py
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from piano_hero.app import App


def main():
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
