#!/usr/bin/env python3
"""Quick sentiment reclassification with progress tracking."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import get_conn
from tools.ai_classifier import _classify_with_fallbacks
import time


def _load_prompt(prompt_file: str) -> str:
    """Load classification prompt from file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / prompt_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def main():
    news_prompt = _load_prompt("news_classifier.txt") 
    
    print("=" * 80)
    print("RECLASSIFICANDO SENTIMENTO")
    print("=" * 80)
    print("Critério: Qualidade da ATUAÇÃO DO ESTADO\n")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            # Count total
            cursor.execute("SELECT COUNT(*) as cnt FROM news_items")
            total_count = cursor.fetchone()["cnt"]
            print(f"Total de notícias: {total_count}\n")
            
            # Fetch with limit to avoid memory issues
            cursor.execute(
                """
                SELECT 
                    n.id, 
                    n.title, 
                    n.content, 
                    n.full_content, 
                    n.sentiment,
                    COALESCE(e.name, 'Governo de Goiás') AS entity_name
                FROM news_items n
                LEFT JOIN monitored_entities e ON n.entity_id = e.id
                ORDER BY n.collected_at DESC
                LIMIT 500
                """
            )
            rows = cursor.fetchall()
            
            reclassified = 0
            unchanged = 0
            errors = 0
            sentiment_counts = {"positivo": 0, "negativo": 0, "neutro": 0}
            
            print(f"Processando {len(rows)} notícias...\n")
            
            for idx, row in enumerate(rows, 1):
                news_id = row["id"]
                old_sentiment = row["sentiment"] or "unknown"
                title = row["title"] or ""
                content = row["content"] or ""
                full_content = row["full_content"] or ""
                entity_name = row["entity_name"] or "Governo de Goiás"

                text_for_classification = f"{title}\n\n{full_content or content}"
                user_prompt = f'Entidade: "{entity_name}"\n\nNotícia:\n{text_for_classification}'

                try:
                    result = _classify_with_fallbacks(news_prompt, user_prompt)
                    if not result:
                        errors += 1
                        status = "✗"
                    else:
                        new_sentiment = result.get("sentiment", "neutro")
                        if new_sentiment != old_sentiment:
                            cursor.execute(
                                "UPDATE news_items SET sentiment = %s WHERE id = %s",
                                (new_sentiment, news_id),
                            )
                            reclassified += 1
                            status = f"→ {new_sentiment}"
                        else:
                            unchanged += 1
                            status = "="
                        
                        if new_sentiment in sentiment_counts:
                            sentiment_counts[new_sentiment] += 1

                except Exception as e:
                    errors += 1
                    status = "✗"

                # Progress every 10 items
                if idx % 10 == 0 or idx == len(rows):
                    print(f"  [{idx:3d}/{len(rows)}] {status:10s} - "
                          f"Alteradas: {reclassified}, Inalteradas: {unchanged}, Erros: {errors}")

                time.sleep(0.3)

            conn.commit()

    print("\n" + "=" * 80)
    print(f"CONCLUÍDO!")
    print(f"  Notícias processadas: {len(rows)}")
    print(f"  Reclassificadas: {reclassified}")
    print(f"  Inalteradas: {unchanged}")
    print(f"  Erros: {errors}")
    print(f"  Distribuição: P:{sentiment_counts['positivo']} N:{sentiment_counts['negativo']} Nt:{sentiment_counts['neutro']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
