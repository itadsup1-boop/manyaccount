import re

file_path = "apps/creator_article/article_pipeline_core.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add import time, random if not exist
if "import random" not in content:
    content = content.replace("import time", "import time\nimport random")

def replace_load_db():
    old = """def _load_db_processed_links():
    try:
        res = supabase_client.table("system_configs").select("config_value").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
        if not res.data:
            return []
        value = res.data[0].get("config_value") or []
        if isinstance(value, list):
            return [_normalize_article_url(item) for item in value if _normalize_article_url(item)]
    except Exception as e:
        print(f"⚠️ Lỗi đọc article_processed_links trong database: {e}")
    return []"""
    new = """def _load_db_processed_links():
    for attempt in range(3):
        try:
            res = supabase_client.table("system_configs").select("config_value").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            if not res.data:
                return []
            value = res.data[0].get("config_value") or []
            if isinstance(value, list):
                return [_normalize_article_url(item) for item in value if _normalize_article_url(item)]
            break
        except Exception as e:
            if attempt == 2:
                print(f"⚠️ Lỗi đọc article_processed_links trong database: {e}")
            else:
                import time, random
                time.sleep(random.uniform(0.5, 1.5))
    return []"""
    return old, new

def replace_save_db():
    old = """def _save_db_processed_links(links):
    clean_links = []
    seen = set()
    for link in links:
        clean_link = _normalize_article_url(link)
        if clean_link and clean_link not in seen:
            seen.add(clean_link)
            clean_links.append(clean_link)
    try:
        existing = supabase_client.table("system_configs").select("config_name").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
        payload = {"config_value": clean_links}
        if existing.data:
            supabase_client.table("system_configs").update(payload).eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
        else:
            supabase_client.table("system_configs").insert({"config_name": ARTICLE_PROCESSED_LINKS_CONFIG_KEY, **payload}).execute()
        return True
    except Exception as e:
        print(f"⚠️ Lỗi lưu article_processed_links trong database: {e}")
        return False"""
    new = """def _save_db_processed_links(links):
    clean_links = []
    seen = set()
    for link in links:
        clean_link = _normalize_article_url(link)
        if clean_link and clean_link not in seen:
            seen.add(clean_link)
            clean_links.append(clean_link)
    for attempt in range(3):
        try:
            existing = supabase_client.table("system_configs").select("config_name").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            payload = {"config_value": clean_links}
            if existing.data:
                supabase_client.table("system_configs").update(payload).eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            else:
                supabase_client.table("system_configs").insert({"config_name": ARTICLE_PROCESSED_LINKS_CONFIG_KEY, **payload}).execute()
            return True
        except Exception as e:
            if attempt == 2:
                print(f"⚠️ Lỗi lưu article_processed_links trong database: {e}")
                return False
            else:
                import time, random
                time.sleep(random.uniform(0.5, 1.5))
    return False"""
    return old, new

def replace_is_article():
    old = """    def _is_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return False
        try:
            res = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
            if len(res.data) > 0:
                return True
        except Exception as e:
            print(f"⚠️ Lỗi check processed_links trên Supabase: {e}")
        if _is_link_in_local_processed(normalized_url):
            return True
        return normalized_url in set(_load_db_processed_links())"""
    new = """    def _is_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return False
        for attempt in range(3):
            try:
                res = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
                if len(res.data) > 0:
                    return True
                break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ Lỗi check processed_links trên Supabase: {e}")
                else:
                    import time, random
                    time.sleep(random.uniform(0.5, 1.5))
        if _is_link_in_local_processed(normalized_url):
            return True
        return normalized_url in set(_load_db_processed_links())"""
    return old, new

def replace_mark_article():
    old = """    def _mark_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return
        _mark_link_local_processed(normalized_url)
        _mark_link_db_processed(normalized_url)
        try:
            existing = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
            if not existing.data:
                supabase_client.table("processed_links").insert({"url": normalized_url}).execute()
        except Exception as e:
            print(f"⚠️ Supabase chặn lưu processed_links, đã lưu database system_configs/local fallback: {e}")"""
    new = """    def _mark_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return
        _mark_link_local_processed(normalized_url)
        _mark_link_db_processed(normalized_url)
        for attempt in range(3):
            try:
                existing = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
                if not existing.data:
                    supabase_client.table("processed_links").insert({"url": normalized_url}).execute()
                break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ Supabase chặn lưu processed_links, đã lưu database system_configs/local fallback: {e}")
                else:
                    import time, random
                    time.sleep(random.uniform(0.5, 1.5))"""
    return old, new

old1, new1 = replace_load_db()
content = content.replace(old1, new1)

old2, new2 = replace_save_db()
content = content.replace(old2, new2)

old3, new3 = replace_is_article()
content = content.replace(old3, new3)

old4, new4 = replace_mark_article()
content = content.replace(old4, new4)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied successfully.")
