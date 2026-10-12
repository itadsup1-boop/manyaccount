from supabase import create_client, Client
import os

SUPABASE_URL = "https://iynwmytfroatvzhbkodf.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml5bndteXRmcm9hdHZ6aGJrb2RmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4MjkxNjYsImV4cCI6MjA4NzQwNTE2Nn0.o9u56KDzfHk26mtNlkVAWH3c-QHUMv4uidVNsbpXVyo"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TIKTOK_CONTENT_PROFILES_CONFIG_KEY = "tiktok_content_profiles"

class SupabaseAPI:
    SUPABASE_URL = "https://iynwmytfroatvzhbkodf.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml5bndteXRmcm9hdHZ6aGJrb2RmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4MjkxNjYsImV4cCI6MjA4NzQwNTE2Nn0.o9u56KDzfHk26mtNlkVAWH3c-QHUMv4uidVNsbpXVyo"
    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase: Client = client
    @staticmethod
    def get_system_config(config_name):
        try:
            res = supabase.table("system_configs").select("config_value").eq("config_name", config_name).single().execute()
            return res.data.get("config_value") if res.data else None
        except:
            return None

    @staticmethod
    def update_system_config(config_name, config_value):
        try:
            data = {"config_name": config_name, "config_value": config_value}
            supabase.table("system_configs").upsert(data).execute()
            return True
        except Exception as e:
            print(f"❌ Lỗi cập nhật config: {e}")
            return False

    @staticmethod
    def get_tiktok_content_profiles():
        profiles = SupabaseAPI.get_system_config(TIKTOK_CONTENT_PROFILES_CONFIG_KEY) or {}
        return profiles if isinstance(profiles, dict) else {}

    @staticmethod
    def attach_tiktok_content_profiles(accounts):
        profiles = SupabaseAPI.get_tiktok_content_profiles()
        if isinstance(accounts, list):
            for account in accounts:
                tiktok_id = account.get("tiktok_id") if isinstance(account, dict) else None
                if tiktok_id and not account.get("content_profile") and tiktok_id in profiles:
                    account["content_profile"] = profiles[tiktok_id]
            return accounts
        if isinstance(accounts, dict):
            tiktok_id = accounts.get("tiktok_id")
            if tiktok_id and not accounts.get("content_profile") and tiktok_id in profiles:
                accounts["content_profile"] = profiles[tiktok_id]
        return accounts

    @staticmethod
    def get_all_accounts():
        res = supabase.table("accounts").select("*").execute()
        return SupabaseAPI.attach_tiktok_content_profiles(res.data)

    @staticmethod
    def get_all_active_accounts():
        res = supabase.table("accounts").select("*").eq("active", True).execute()
        return SupabaseAPI.attach_tiktok_content_profiles(res.data)

    @staticmethod
    def get_account_by_id(tiktok_id):
        try:
            # Do not use ``single()`` here: a transient 0-row response or a
            # duplicate legacy row makes Supabase raise and the worker used to
            # report only the misleading "config not found" message.  Taking
            # the first matching row keeps the worker resilient while still
            # preserving the active-account check in the scheduler.
            res = supabase.table("accounts").select("*").eq("tiktok_id", tiktok_id).execute()
            rows = res.data or []
            if not rows:
                return None
            return SupabaseAPI.attach_tiktok_content_profiles(rows[0])
        except Exception as exc:
            print(
                f"⚠️ Supabase get_account_by_id({tiktok_id}) lỗi: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

    @staticmethod
    def save_account(account_data):
        try:
            supabase.table("accounts").upsert(account_data).execute()
            return True
        except Exception as e:
            print(f"❌ Lỗi lưu account: {e}")
            return False

    @staticmethod
    def delete_account(tiktok_id):
        try:
            supabase.table("accounts").delete().eq("tiktok_id", tiktok_id).execute()
            return True
        except:
            return False

    @staticmethod
    def get_channel_videos_db(tiktok_id, channel_url):
        try:
            res = supabase.table("channel_videos").select("video_list").eq("tiktok_id", tiktok_id).eq("channel_url", channel_url).execute()
            if res.data:
                return res.data[0].get("video_list", [])
            return []
        except Exception as e:
            print(f"Lỗi lấy video từ DB: {e}")
            return []

    @staticmethod
    def update_channel_videos_db(tiktok_id, channel_url, video_list):
        try:
            payload = {
                "tiktok_id": tiktok_id,
                "channel_url": channel_url,
                "video_list": video_list
            }
            supabase.table("channel_videos").upsert(payload, on_conflict="tiktok_id, channel_url").execute()
            return True
        except Exception as e:
            print(f"Lỗi lưu video lên DB: {e}")
            return False

    @staticmethod
    def delete_channel_videos_db(tiktok_id, channel_url):
        try:
            supabase.table("channel_videos").delete().eq("tiktok_id", tiktok_id).eq("channel_url", channel_url).execute()
            return True
        except Exception as e:
            print(f"Lỗi xóa video trên DB: {e}")
            return False

    # ================= QUẢN LÝ TIẾN ĐỘ & FILE =================
    @staticmethod
    def update_channel_tracking(tiktok_id, channel_url, last_url, new_index):
        res = supabase.table("accounts").select("channels").eq("tiktok_id", tiktok_id).single().execute()
        channels = res.data.get("channels", [])

        updated = False
        for channel in channels:
            if channel.get("url") == channel_url:
                channel["last_video_url"] = last_url
                channel["video_index"] = new_index
                updated = True
                break
        if updated:
            supabase.table("accounts").update({"channels": channels}).eq("tiktok_id", tiktok_id).execute()
            return True
        return False

    @staticmethod
    def download_asset(bucket_name, storage_path, local_dir, file_name):
        if not file_name: return None
        try:
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, file_name)
            full_storage_path = f"{storage_path}/{file_name}"
            res = supabase.storage.from_(bucket_name).download(full_storage_path)
            with open(local_path, "wb") as f:
                f.write(res)
            return local_path
        except Exception as e:
            print(f"   ⚠️ Lỗi kéo file {file_name} từ Supabase: {e}")
            return os.path.join(local_dir, file_name)

    @classmethod
    def get_list_storage_files(cls, bucket_name, folder_name, *, quiet=False):
        try:
            import sys
            current_module = sys.modules[__name__]
            db = getattr(cls, 'client', None) or getattr(cls, 'supabase', None) or getattr(cls, '_client', None)
            if not db:
                db = getattr(current_module, 'supabase', None) or getattr(current_module, 'client', None)

            if db:
                res = db.storage.from_(bucket_name).list(folder_name)
                if isinstance(res, list):
                    return [f.get('name') for f in res if isinstance(f, dict) and f.get('name') and f.get('name') != '.emptyFolderPlaceholder']
            return []
        except Exception as e:
            if not quiet:
                print(f"Lỗi đọc Storage Supabase: {e}")
            return []
