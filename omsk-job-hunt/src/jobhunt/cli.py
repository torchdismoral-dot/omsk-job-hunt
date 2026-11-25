from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .config import Settings, load_config, load_dotenv
from .db import DB
from .normalize import Vacancy, from_superjob, from_trudvsem
from .pipeline import build
from .render import facts_text
from .ranker import rank


def format_vacancy(index: int, vacancy: Vacancy, home: tuple[float, float] | None = None) -> str:
    line = f"{index}. {vacancy.title} — {vacancy.company or 'компания не указана'}"
    return f"{line}\n   {facts_text(vacancy, home)}\n   {vacancy.url}"


def _from_fixtures(directory: pathlib.Path, settings: Settings) -> list[Vacancy]:
    raw_superjob: list[dict] = []
    raw_trudvsem: list[dict] = []
    sj_path = directory / "superjob_omsk.json"
    tv_path = directory / "trudvsem_omsk.json"
    if sj_path.exists():
        raw_superjob = json.loads(sj_path.read_text(encoding="utf-8"))["objects"]
    if tv_path.exists():
        data = json.loads(tv_path.read_text(encoding="utf-8"))
        raw_trudvsem = [item["vacancy"] for item in data["results"]["vacancies"]]
    return build(raw_superjob, raw_trudvsem, settings)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobhunt")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    top = sub.add_parser("top", help="показать топ вакансий")
    top.add_argument("--by", choices=["date", "salary", "distance"], default="date")
    top.add_argument("--limit", type=int, default=None)
    top.add_argument("--db", default="jobhunt.db")
    top.add_argument("--fixtures", default=None, help="каталог с JSON-фикстурами")

    refresh = sub.add_parser("refresh", help="забрать вакансии из API и сохранить")
    refresh.add_argument("--db", default="jobhunt.db")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    load_dotenv()
    settings = load_config(args.config)

    if args.command == "refresh":
        from .pipeline import refresh

        stats = refresh(settings, DB(args.db))
        print(
            f"получено {stats['fetched']}, подошло {stats['relevant']}, "
            f"новых {stats['fresh']}, всего в базе {stats['total']}"
        )
        return 0

    if args.command == "top":
        if args.fixtures:
            vacancies = _from_fixtures(pathlib.Path(args.fixtures), settings)
        else:
            db = DB(args.db)
            vacancies = db.all()
            db.close()
        if not vacancies:
            print("Вакансий нет. Сначала запусти: python -m jobhunt.cli refresh")
            return 1
        limit = args.limit or settings.top_n
        for index, vacancy in enumerate(rank(vacancies, args.by, settings.home)[:limit], 1):
            print(format_vacancy(index, vacancy, settings.home))
            print()
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
