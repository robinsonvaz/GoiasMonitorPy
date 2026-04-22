from __future__ import annotations

import json

from db import execute, parse_json_list, query_all
from tools.ai_classifier import enrich_people_mentioned


def main() -> None:
    rows = query_all(
        """
        SELECT
            n.id,
            n.title,
            n.content,
            n.people_mentioned,
            COALESCE(me.name, '') AS entity_name
        FROM news_items n
        LEFT JOIN monitored_entities me ON me.id = n.entity_id
        """
    )

    updated = 0
    unchanged = 0

    for row in rows:
        current = parse_json_list(row.get("people_mentioned"))
        merged = enrich_people_mentioned(
            current_mentions=current,
            title=row.get("title") or "",
            content=row.get("content") or "",
            entity_name=row.get("entity_name") or "",
        )

        if merged == current:
            unchanged += 1
            continue

        execute(
            "UPDATE news_items SET people_mentioned = %s WHERE id = %s",
            (json.dumps(merged, ensure_ascii=False), row["id"]),
        )
        updated += 1

    print(f"Total news: {len(rows)}")
    print(f"Updated: {updated}")
    print(f"Unchanged: {unchanged}")


if __name__ == "__main__":
    main()
