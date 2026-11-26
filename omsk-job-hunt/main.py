"""Точка входа для PaaS (Amvera, Docker): код лежит в src/, добавляем его в путь сами.

Так команда запуска не зависит от того, прогоняет ли платформа её через shell
и подставляет ли PYTHONPATH.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from jobhunt.bot.app import main

if __name__ == "__main__":
    asyncio.run(main())
