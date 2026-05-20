from db import execute, query_one
updated = execute("UPDATE news_items SET full_content = COALESCE(full_content, full_text, content) WHERE full_content IS NULL OR full_content = ''")
full_content_row = query_one("SELECT COUNT(*) AS total FROM news_items WHERE full_content IS NOT NULL AND full_content <> ''")
print("Backfill full_content:", updated)
print("full_content preenchido:", full_content_row["total"])
