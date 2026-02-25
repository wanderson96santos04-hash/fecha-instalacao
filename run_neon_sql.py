from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from app.db.session import engine


def main() -> None:
    sql_path = Path("neon.sql")
    if not sql_path.exists():
        raise SystemExit("Arquivo neon.sql não encontrado na raiz do projeto.")

    sql = sql_path.read_text(encoding="utf-8")

    # Executa tudo dentro de uma transação
    with engine.begin() as conn:
        conn.execute(text(sql))

    print("✅ neon.sql aplicado com sucesso no banco:", engine.url)


if __name__ == "__main__":
    main()