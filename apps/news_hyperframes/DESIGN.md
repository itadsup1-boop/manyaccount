# Swiss Ledger — News Video Studio

## Purpose

An editorial vertical system for Vietnamese economic and public-interest news.
It turns verified facts from `News Video Production JSON v2` into a calm,
high-contrast 9:16 video. It is designed for 18–35 year-old viewers who need
to understand the point quickly, not be distracted by spectacle.

## Visual direction

- Background: charcoal `#13171D`.
- Primary text: warm ivory `#F5F1E8`.
- Secondary text: cool grey `#AEB4BF`.
- One editorial accent: amber `#F4A340`, reserved for key numbers, the active
  beat marker and short dividers.
- Typeface: **Outfit**, using its weight and scale rather than a mix of
  unrelated display faces. Numeric data uses tabular figures.
- Layout: a left editorial rail, generous safe margins, one visual focal point
  per scene and short, sentence-case captions.

## Motion direction

- Medium-energy editorial pace: each beat enters with a 0.34–0.46 second
  vertical push and fades into the next beat.
- A thin amber progress rail advances once per beat. Data lines count or wipe
  on; they do not bounce or loop.
- Every scene uses a deterministic GSAP entrance. No `repeat:-1`, random
  animation, animated gradients, fake camera shake or exit animation between
  scenes.

## Real-media and rights constraints

- Only a local asset that is explicitly recorded as `licensed_real_stock` or
  `owned_original` can be placed as photo/video B-roll.
- Never use images, video, screenshots, logos or watermarks from the source
  publisher or article. Do not crop, blur, remove or recreate a watermark.
- No AI-generated imagery. If a beat has no approved real asset, use the
  structured data-card fallback defined in its JSON instead.

## Avoid

- Generic TV-news lower thirds, neon/glass treatment, loud red alert banners,
  dense charts, all-caps paragraph text, brand logos, and a separate visual
  for every sentence.
