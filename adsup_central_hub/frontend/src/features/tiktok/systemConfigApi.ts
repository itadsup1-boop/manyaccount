export type ScheduleConfig = {
  crawl_times: string[];
  nurture_windows: unknown[];
};

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

export function normalizeScheduleTimes(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(
    new Set(
      value
        .map((item) => String(item ?? '').trim())
        .filter((item) => TIME_PATTERN.test(item)),
    ),
  ).sort();
}

async function readJson(response: Response) {
  let data: any;
  try {
    data = await response.json();
  } catch {
    throw new Error('Máy chủ trả về dữ liệu không hợp lệ.');
  }

  if (!response.ok || data?.error) {
    throw new Error(data?.error || `Máy chủ báo lỗi ${response.status}.`);
  }
  return data;
}

export async function fetchScheduleConfig(signal?: AbortSignal): Promise<ScheduleConfig> {
  const response = await fetch('/api/system/config/schedule_config', {
    cache: 'no-store',
    signal,
  });
  const data = await readJson(response);
  return {
    crawl_times: normalizeScheduleTimes(data?.crawl_times),
    nurture_windows: Array.isArray(data?.nurture_windows) ? data.nurture_windows : [],
  };
}

export async function saveScheduleConfig(crawlTimes: string[]): Promise<ScheduleConfig> {
  const payload: ScheduleConfig = {
    crawl_times: normalizeScheduleTimes(crawlTimes),
    nurture_windows: [],
  };
  const response = await fetch('/api/system/config/schedule_config', {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await readJson(response);
  return payload;
}
