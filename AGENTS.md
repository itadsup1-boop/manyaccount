# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python automation suite. Product entry points live in `apps/`: article creation, Facebook processing, Telegram control, and TikTok uploading each have their own package. Reusable orchestration, media helpers, and external-service clients belong under `shared/core`, `shared/modules`, and `shared/services`. Prompts and schedules are in `config/`; operator launchers are in `scripts/`. `adsup_central_hub/` contains a FastAPI backend and a React/TypeScript Vite frontend. Treat `data/`, `shared/data/`, browser profiles, logs, databases, and generated media as runtime state—not source or test fixtures.

## Build, Test, and Development Commands

Create the main Python environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run a desktop workflow with `./scripts/khoi_dong_tool_bao_mang.sh`, `./scripts/khoi_dong_tool_facebook.sh`, or `./scripts/khoi_dong_upload_tiktok.sh`. For the web UI:

```bash
cd adsup_central_hub/frontend
npm install
npm run dev
npm run lint
npm run build
```

`adsup_central_hub/start_hub.sh` starts the backend, frontend, and a Cloudflare tunnel; use it only when that full local stack is intended.

## Coding Style & Naming Conventions

Use four spaces in Python, follow PEP 8 where practical, and keep imports grouped standard-library, third-party, then local. Name modules/functions `snake_case`, classes `PascalCase`, and constants `UPPER_SNAKE_CASE`. Keep service integrations in `shared/services` rather than duplicating API logic. React components use `PascalCase.tsx`; use two-space indentation in TypeScript/CSS and run Oxlint before review. Avoid unrelated formatting churn in legacy files.

## Testing Guidelines

There is no unified test framework or coverage gate yet. At minimum, syntax-check changed Python packages with `python -m compileall apps shared adsup_central_hub/backend`, then exercise the affected launcher or pipeline with non-production inputs. `shared/modules/test_ffmpeg_split.py` is a manual FFmpeg smoke script requiring `test.mp4`. Add automated tests as `test_*.py`, isolate network/browser dependencies, and document any required fixture media.

## Commit & Pull Request Guidelines

Recent history uses short imperative subjects such as `Update ...` and `Remove ...`; retain that style but name the scope clearly, for example `Update article URL deduplication`. Keep commits focused and exclude generated profiles, credentials, media, and logs. Pull requests should explain the user-visible change, list validation commands, link the relevant issue, and include screenshots for desktop or hub UI changes. Call out configuration, database, or external-service impacts explicitly.

## Security & Configuration

Store secrets only in `.env` or ignored credential files. Never commit Supabase keys, Google credentials, cookies, tokens, browser profiles, or production channel state. Review `git status` carefully before every commit because automation runs update many local artifacts.
