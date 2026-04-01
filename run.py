"""PyInstaller entry point — wraps cc_feishu_bridge.main:main for binary builds."""
from cc_feishu_bridge.main import main

if __name__ == "__main__":
    main()
