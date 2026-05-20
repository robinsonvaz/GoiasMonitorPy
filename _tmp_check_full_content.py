from db import query_one
all_row = query_one("SELECT COUNT(*) AS total FROM news_items")
full_text_row = query_one("SELECT COUNT(*) AS total FROM news_items WHERE full_text IS NOT NULL AND full_text <> ''")
full_content_row = query_one("SELECT COUNT(*) AS total FROM news_items WHERE full_content IS NOT NULL AND full_content <> ''")
print("total:", all_row["total"])
print("full_text preenchido:", full_text_row["total"])
print("full_content preenchido:", full_content_row["total"])
