-- Chạy sau khi đã dọn các dòng trùng hiện có trong facebook_sources/
-- facebook_videos. Không tự xóa dữ liệu cũ trong migration này.

create unique index if not exists facebook_sources_active_url_unique
    on public.facebook_sources (source_url)
    where is_active = true;

create unique index if not exists facebook_videos_source_video_unique
    on public.facebook_videos (source_id, facebook_video_id);

create index if not exists facebook_videos_hash_idx
    on public.facebook_videos (file_hash);
