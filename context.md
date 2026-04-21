# CloudMetrix_Engine - System Constitution

This document serves as the authoritative guide and "constitution" for all AI Agent sessions within the `CloudMetrix_Engine` project. It defines the architecture, design standards, and operational boundaries to ensure consistency and efficiency.

## 1. Project Overview
- **Project Name:** CloudMetrix_Engine
- **Objective:** To provide a production-ready automation engine for syncing TikTok media and publishing it to Meta Business Suite (Facebook Reels/Posts).
- **Core Workflow:**
  1. Synchronize media from target TikTok creators (Source).
  2. Manage and edit content metadata via the Automation Hub (Frontend).
  3. Automate the browser-based upload sequence to Meta Business Suite using the Playwright engine.

## 2. System Architecture & Components

### Backend (Python)
- **`app.py`**: The central Flask application serving the API and Dashboard.
- **`uploader.py`**: Manages global posting states, telemetry logs, and high-level uploader coordination.
- **`playwright_uploader.py`**: The heavy-lifting browser automation layer. Uses Playwright to interact with Meta Business Suite.
- **`downloader.py`**: Handles TikTok media extraction and JIT (Just-In-Time) format fixes.
- **`scheduler.py`**: Manages background automated tasks.

### Frontend (HTML/JS/Vanilla CSS)
- Located in `templates/`.
- **`editor.html`**: The main Automation Hub interface. Handles filtering, selection, and manual triggering of posts.
- **`dashboard.html`**: Overview of system statistics and deep-link shortcuts.
- **`base.html`**: Global layout, theme management (Dark/Light/System), and universal notification systems (SOP Brand Toast).

### Data Persistence
- **`data/content_map.csv`**: Record of all synced media, metadata, and publication status.
- **`data/accounts.json`**: Management of Facebook profiles and sessions.

## 3. UI/UX Style Guide
All interface development must adhere to the **Minimalist European Design** philosophy:
- **Tone & Mood:** Professional, high-end SaaS aesthetic.
- **Color Palette:** Strictly Blue and Black tones. Avoid vibrant, high-contrast primary colors (red/green/yellow) except for critical status indicators (error/success toasts).
- **Typography:** Modern sans-serif fonts (e.g., Inter, Outfit) with generous whitespace and sentence-case labels.
- **Interactivity:** Subtle glassmorphism, smooth micro-animations, and theme-aware components.

## 4. Token Optimization & Agent Behaviors
To maximize efficiency and conserve context tokens, the following rules apply:
- **Scope Restriction:** NEVER recursively read directories or files within `.venv/`, `__pycache__/`, or `data/` (unless specifically analyzing a small sample of the CSV).
- **Media Cleanup:** Ignore orphaned or broken `.png`/`.jpg` files in the root directory unless explicitly asked to fix media paths.
- **Discovery Strategy:** Prioritize `git diff` or `tail` for checking recent changes. Avoid reading entire files if only a specific function or block is relevant.
- **Persistence:** Always verify that proposed changes align with the existing `SOP Brand Identity` and the `CSV_LOCK` thread-safety pattern.

## 5. Current Implementation Focus
- **Finalizing Progress Visualization:** Ensuring per-video progress bars in `editor.html` are accurately updated by the `POST_STATE` from the backend.
- **Bulk Action Stability:** Refining the "Post Selected" workflow to be resilient to browser session timeouts.
- **Telemtry Feedback:** Fixing synchronization issues between the `playwright_uploader.py` telemetry logs and the `Live Telemetry` container in the Hub.
- **Format Fixes**: Ensuring JIT re-downloads correctly handle legacy `.mp3` files and missing `ffmpeg` scenarios.

---
*Last Updated: 2026-04-19*
