import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC = BASE_DIR / "docs" / "schema_dump.sql"
DST = BASE_DIR / "docs" / "schema_mysql.sql"
DB_NAME = "goiasmonitor"


def convert_array(match: re.Match) -> str:
    inner = (match.group(1) or "").strip()
    if not inner:
        return "JSON_ARRAY()"
    return f"JSON_ARRAY({inner})"


def convert_insert(stmt: str) -> str:
    stmt = stmt.replace("public.", "")
    stmt = re.sub(r"ARRAY\[(.*?)\](?:::text\[\])?", convert_array, stmt, flags=re.DOTALL)
    stmt = re.sub(
        r"'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\+00:00'",
        r"'\1 \2'",
        stmt,
    )
    return stmt


def extract_insert_statements(content: str) -> list[str]:
    starts = [m.start() for m in re.finditer(r"INSERT INTO\s+public\.", content)]
    statements: list[str] = []

    for start in starts:
        i = start
        in_quote = False
        while i < len(content):
            ch = content[i]
            if ch == "'":
                # PostgreSQL escapes single quote as doubled quote ('').
                if in_quote and i + 1 < len(content) and content[i + 1] == "'":
                    i += 2
                    continue
                in_quote = not in_quote
            elif ch == ";" and not in_quote:
                statements.append(content[start : i + 1])
                break
            i += 1

    return statements


def main() -> None:
    content = SRC.read_text(encoding="utf-8")

    inserts = extract_insert_statements(content)

    converted_inserts = []
    for stmt in inserts:
        # Ignore INSERT statements from function bodies (e.g., NEW.id in triggers).
        if "NEW." in stmt:
            continue
        if not re.search(r"INSERT INTO\s+public\.(profiles|monitored_entities|news_items|alerts)\b", stmt):
            continue
        converted_inserts.append(convert_insert(stmt))

    header = f"""-- Auto-generated from docs/schema_dump.sql
-- Target: MySQL 8+

DROP DATABASE IF EXISTS {DB_NAME};
CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE {DB_NAME};

CREATE TABLE profiles (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id CHAR(36) NOT NULL UNIQUE,
  full_name TEXT NULL,
  avatar_url TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE monitored_entities (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name TEXT NOT NULL,
  entity_type VARCHAR(80) NOT NULL DEFAULT 'orgao',
  description TEXT NULL,
  keywords JSON NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by CHAR(36) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE news_items (
  id CHAR(36) NOT NULL PRIMARY KEY,
  entity_id CHAR(36) NULL,
  title TEXT NOT NULL,
  content TEXT NULL,
  source_url TEXT NULL,
  source_name VARCHAR(255) NULL,
  classification ENUM('midia_negativa','nomeacao','exoneracao','substituicao','troca','movimentacao','acao_judicial','outro') NOT NULL DEFAULT 'outro',
  sentiment ENUM('positivo','negativo','neutro') NOT NULL DEFAULT 'neutro',
  people_mentioned JSON NULL,
  published_at DATETIME(6) NULL,
  collected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_news_items_entity (entity_id),
  INDEX idx_news_items_sentiment (sentiment),
  INDEX idx_news_items_classification (classification),
  INDEX idx_news_items_collected (collected_at),
  CONSTRAINT fk_news_entity FOREIGN KEY (entity_id) REFERENCES monitored_entities(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE alerts (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id CHAR(36) NOT NULL,
  news_item_id CHAR(36) NULL,
  title TEXT NOT NULL,
  message TEXT NULL,
  alert_type VARCHAR(80) NOT NULL DEFAULT 'info',
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_alerts_user (user_id),
  INDEX idx_alerts_unread (user_id, is_read),
  CONSTRAINT fk_alert_news FOREIGN KEY (news_item_id) REFERENCES news_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS=0;
"""

    footer = "\nSET FOREIGN_KEY_CHECKS=1;\n"

    output = header + "\n\n".join(converted_inserts) + "\n" + footer
    DST.write_text(output, encoding="utf-8")

    print(f"Arquivo gerado: {DST}")
    print(f"Total de inserts convertidos: {len(converted_inserts)}")


if __name__ == "__main__":
    main()
