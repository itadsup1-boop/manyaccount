"""Crawler feed Facebook Group: chỉ nhận bài trong đúng nhóm và có video."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .source_config import extract_group_key, extract_video_id, parse_group_post_url


# Playwright chạy đoạn này trong trình duyệt. Facebook hiện đặt bài chính trong
# ``[aria-posinset]`` của feed; ``[role=article]`` thường là bình luận. Giữ
# fallback article để tương thích DOM cũ và các fixture kiểm thử.
GROUP_POST_EXTRACTOR_JS = r"""
({ expectedGroupKey }) => {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const postRef = href => {
    try {
      const baseUrl = window.location.origin === 'null'
        ? 'https://www.facebook.com'
        : window.location.origin;
      const url = new URL(href, baseUrl);
      const match = url.pathname.match(/\/groups\/([^/]+)\/(?:posts|permalink)\/(\d+)/i);
      if (match) return { groupKey: match[1], postId: match[2], href: url.href };
      const group = url.pathname.match(/\/groups\/([^/]+)/i);
      const multi = url.searchParams.get('multi_permalinks');
      if (group && /^\d+$/.test(multi || '')) {
        return { groupKey: group[1], postId: multi, href: url.href };
      }
    } catch (_) {}
    return null;
  };
  const videoIdFrom = href => {
    const text = String(href || '');
    for (const regex of [/\/videos\/(\d+)/i, /\/reel\/(\d+)/i, /[?&]v=(\d+)/i, /story_fbid=(\d+)/i]) {
      const match = text.match(regex);
      if (match) return match[1];
    }
    return '';
  };

  const feedPosts = Array.from(document.querySelectorAll(
    '[role="feed"] [aria-posinset]'
  ));
  const postContainers = feedPosts.length > 0
    ? feedPosts
    : Array.from(document.querySelectorAll('[role="article"]'));

  const results = [];
  for (const post of postContainers) {
    const anchors = Array.from(post.querySelectorAll('a[href]'));
    const ref = anchors.map(anchor => postRef(anchor.href)).find(item =>
      item && item.groupKey.toLowerCase() === String(expectedGroupKey).toLowerCase()
    );
    if (!ref) continue;

    const nativeVideos = Array.from(post.querySelectorAll('video'));
    const videoIdNodes = Array.from(post.querySelectorAll('[data-video-id]'));
    // Chỉ công nhận player/video nằm trong chính bài. Không dùng link
    // /reel hoặc /watch đơn lẻ vì đó có thể chỉ là link được dán trong caption.
    if (nativeVideos.length === 0 && videoIdNodes.length === 0) continue;

    let videoId = '';
    for (const node of videoIdNodes) {
      const candidate = clean(node.getAttribute('data-video-id'));
      if (/^\d+$/.test(candidate)) { videoId = candidate; break; }
    }
    if (!videoId) {
      videoId = anchors.map(anchor => videoIdFrom(anchor.href)).find(Boolean) || '';
    }

    const messageNodes = Array.from(post.querySelectorAll(
      '[data-ad-preview="message"], [data-ad-comet-preview="message"]'
    ));
    let caption = clean(messageNodes.map(node => node.innerText).join(' '));
    if (!caption) {
      const directional = Array.from(post.querySelectorAll('[dir="auto"]'))
        .map(node => clean(node.innerText))
        .filter(text => text.length >= 8);
      caption = directional.sort((a, b) => b.length - a.length)[0] || '';
    }

    let publishedAt = '';
    const timeNode = post.querySelector('time[datetime]');
    if (timeNode) publishedAt = clean(timeNode.getAttribute('datetime'));
    if (!publishedAt) {
      const unixNode = post.querySelector('[data-utime]');
      const unixValue = Number(unixNode && unixNode.getAttribute('data-utime'));
      if (Number.isFinite(unixValue) && unixValue > 0) {
        publishedAt = new Date(unixValue * 1000).toISOString();
      }
    }
    results.push({
      group_key: ref.groupKey,
      post_id: ref.postId,
      post_url: ref.href,
      video_id: videoId,
      caption,
      published_at: publishedAt,
      has_native_video: true,
    });
  }
  return results;
}
"""


def _published_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_group_video_items(
    candidates: Iterable[Mapping[str, Any]],
    *,
    source_url: str,
    max_videos: int,
    max_age_hours: int = 0,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Lọc lần hai ở Python để DOM giả hoặc dữ liệu lỗi không lọt pipeline."""

    group_key = extract_group_key(source_url)
    if not group_key:
        return []
    cutoff = None
    if max_age_hours > 0:
        current = now or datetime.now(timezone.utc)
        cutoff = current.astimezone(timezone.utc) - timedelta(hours=max_age_hours)

    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not bool(candidate.get("has_native_video")):
            continue
        post_ref = parse_group_post_url(candidate.get("post_url"), group_key)
        if not post_ref:
            continue
        published = _published_datetime(candidate.get("published_at"))
        if cutoff and published and published < cutoff:
            continue
        raw_video_id = str(candidate.get("video_id") or "").strip()
        video_id = raw_video_id if raw_video_id.isdigit() else ""
        if not video_id:
            video_id = extract_video_id(candidate.get("post_url")) or post_ref.post_id
        item = {
            "video_id": video_id,
            "post_id": post_ref.post_id,
            "group_id": post_ref.group_key,
            "url": post_ref.canonical_url,
            "post_url": post_ref.canonical_url,
            "caption": " ".join(str(candidate.get("caption") or "").split())[:2000],
            "published_at": published.isoformat() if published else "",
            "source_type": "group",
        }
        unique.setdefault(post_ref.post_id, item)

    def sort_key(item: Mapping[str, Any]) -> tuple[int, float]:
        parsed = _published_datetime(item.get("published_at"))
        return (1 if parsed else 0, parsed.timestamp() if parsed else 0.0)

    return sorted(unique.values(), key=sort_key, reverse=True)[:max_videos]


def crawl_group_video_posts(
    page: Any,
    *,
    source_url: str,
    max_videos: int,
    max_age_hours: int = 0,
    max_scrolls: int = 15,
) -> list[dict[str, Any]]:
    group_key = extract_group_key(source_url)
    collected: dict[str, Mapping[str, Any]] = {}
    stagnant_rounds = 0

    for scroll_index in range(max_scrolls + 1):
        raw = page.evaluate(GROUP_POST_EXTRACTOR_JS, {"expectedGroupKey": group_key})
        before = len(collected)
        for candidate in raw or []:
            post_id = str(candidate.get("post_id") or "")
            if post_id:
                collected[post_id] = candidate
        if len(collected) == before:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0

        items = build_group_video_items(
            collected.values(),
            source_url=source_url,
            max_videos=max_videos,
            max_age_hours=max_age_hours,
        )
        enough_results = len(items) >= max_videos
        scanned_enough = scroll_index >= 6
        no_more_results = bool(collected) and scanned_enough and stagnant_rounds >= 4
        if enough_results or no_more_results or scroll_index >= max_scrolls:
            return items
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.85, 900))")
        page.wait_for_timeout(1300)
    return []
