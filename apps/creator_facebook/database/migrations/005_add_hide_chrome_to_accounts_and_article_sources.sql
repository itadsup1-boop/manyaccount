-- Cho phép từng nguồn TikTok / bài báo chọn chạy Chrome nền (headless)
-- hoặc hiện cửa sổ. Mặc định false để giữ nguyên hành vi cũ.

alter table if exists public.accounts
    add column if not exists hide_chrome boolean not null default false;

alter table if exists public.article_sources
    add column if not exists hide_chrome boolean not null default false;
