#!/usr/bin/env python3
"""Reclassify sentiment of all captured news and social mentions using new criteria."""
from __future__ import annotations

import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import get_conn
from tools.ai_classifier import _classify_with_fallbacks


def _load_prompt(prompt_file: str) -> str:
    """Load classification prompt from file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / prompt_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _reclassify_news_items(dry_run: bool = False, verbose: bool = False) -> dict:
    """Reclassify all news items using new sentiment criteria."""
    news_prompt = _load_prompt("news_classifier.txt")
    stats = {
        "total": 0,
        "reclassified": 0,
        "unchanged": 0,
        "errors": 0,
        "sentiment_changes": {"positivo": 0, "negativo": 0, "neutro": 0, "unknown": 0},
    }

    with get_conn() as conn:
        with conn.cursor() as cursor:
            # Fetch all news items with entity names via JOIN
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
                """
            )
            rows = cursor.fetchall()
            stats["total"] = len(rows)

            for row in rows:
                news_id = row["id"]
                old_sentiment = row["sentiment"] or "unknown"
                title = row["title"] or ""
                content = row["content"] or ""
                full_content = row["full_content"] or ""
                entity_name = row["entity_name"] or "Governo de Goiás"

                # Prepare user prompt with full content
                text_for_classification = f"{title}\n\n{full_content or content}"
                user_prompt = f'Entidade monitorada: "{entity_name}"\n\nNotícia:\n{text_for_classification}'

                try:
                    result = _classify_with_fallbacks(news_prompt, user_prompt)
                    if not result:
                        if verbose:
                            print(f"  ✗ {news_id}: Falha ao classificar (sem resposta de IA)")
                        stats["errors"] += 1
                        continue

                    new_sentiment = result.get("sentiment", "neutro")
                    ai_provider = result.get("ai_provider", "unknown")

                    # Update database
                    if not dry_run:
                        cursor.execute(
                            """
                            UPDATE news_items
                            SET sentiment = %s, ai_provider = %s
                            WHERE id = %s
                            """,
                            (new_sentiment, ai_provider, news_id),
                        )

                    # Track statistics
                    if new_sentiment != old_sentiment:
                        stats["reclassified"] += 1
                        if verbose:
                            print(
                                f"  ✓ {news_id}: {old_sentiment} → {new_sentiment} "
                                f"({ai_provider})"
                            )
                    else:
                        stats["unchanged"] += 1
                        if verbose:
                            print(f"  = {news_id}: Mantém-se {old_sentiment}")

                    # Track sentiment distribution
                    if new_sentiment in stats["sentiment_changes"]:
                        stats["sentiment_changes"][new_sentiment] += 1

                except Exception as e:
                    if verbose:
                        print(f"  ✗ {news_id}: Erro - {str(e)[:80]}")
                    stats["errors"] += 1

                # Rate limiting to avoid API throttling
                time.sleep(0.5)

            if not dry_run:
                conn.commit()

    return stats




def main() -> int:
    """Main entry point."""
    parser = ArgumentParser(
        description="Reclassify sentiment of all news with new criteria (atuação do Estado)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without updating database",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show details for each item",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("RECLASSIFICANDO SENTIMENTO COM NOVOS CRITÉRIOS")
    print("=" * 80)
    print(
        "Critério: Qualidade da ATUAÇÃO DO ESTADO"
        " (avaliação de como o Estado agiu)\n"
    )

    if args.dry_run:
        print("⚠️  MODO SECO (dry-run) - Nenhuma alteração será feita\n")

    print("\n📰 RECLASSIFICANDO TODAS AS NOTÍCIAS...")
    print("-" * 80)
    news_stats = _reclassify_news_items(dry_run=args.dry_run, verbose=args.verbose)

    # Summary
    print("\n" + "=" * 80)
    total = news_stats["total"]
    reclassified = news_stats["reclassified"]
    unchanged = news_stats["unchanged"]
    errors = news_stats["errors"]

    print(f"RESUMO:")
    print(f"  Total processado: {total} notícias")
    print(f"  Reclassificadas: {reclassified} ({100*reclassified/total:.1f}%)" if total else "  Reclassificadas: 0")
    print(f"  Inalteradas: {unchanged}")
    print(f"  Erros: {errors}")
    print(f"  Distribuição final: {json.dumps(news_stats['sentiment_changes'], ensure_ascii=False)}")

    if args.dry_run:
        print(f"\n⚠️  Modo seco - nenhuma alteração foi feita ao banco de dados")
    else:
        print(f"\n✅ Reclassificação concluída e salva no banco de dados")

    print("=" * 80)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
