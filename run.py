"""PyInstaller entry point — wraps src.main:main for binary builds."""
from src.main import main

if __name__ == "__main__":
    main()
