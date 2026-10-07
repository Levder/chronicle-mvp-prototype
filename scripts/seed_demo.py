#!/usr/bin/env python3
"""Seed three demo scenarios: verified / rumor copies / chronology conflict."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.models import ArticleIn
from app.db.database import SessionLocal, init_db
from app.services.pipeline import process_article

VERIFIED = """
5 березня 2022 року в Бучі зафіксовано обстріл житлового кварталу.
Місцеві жителі повідомляють про пошкодження будинків на вулиці Яблунській.
Є первинне відео з геомітками та два незалежні репортажі місцевих журналістів.
Офіційні структури пізніше підтвердили факт обстрілу в цей день.
"""

RUMOR = """
Анонімний телеграм-канал стверджує, що в Ірпені сталася подія невідомого характеру.
Текст передруковано п'ятьма сайтами без змін і без первинних доказів.
Джерела посилаються одне на одного, незалежних підтверджень немає.
"""

CONFLICT = """
У статті зазначено, що велика подія в Ірпені відбулася 20 лютого 2022 року.
Однак за усталеним таймлайном активні бойові дії в місті розпочалися пізніше.
Дата суперечить відомим хронологічним маркерам. Потрібна глибока перевірка.
"""


async def main():
    await init_db()
    async with SessionLocal() as session:
        for title, text in [
            ("Буча: обстріл 5 березня (verified demo)", VERIFIED),
            ("Ірпінь: анонімний передрук (rumor demo)", RUMOR),
            ("Ірпінь: конфлікт дат (chronology demo)", CONFLICT),
        ]:
            result = await process_article(
                session,
                ArticleIn(title=title, raw_text=text, source_domain="demo.local"),
            )
            print(result.get("queue"), result.get("event_id"), result.get("E"), result.get("M"))


if __name__ == "__main__":
    asyncio.run(main())
