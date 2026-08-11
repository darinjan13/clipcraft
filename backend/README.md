# ClipCraft Backend

Run locally from the repository root:

```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Configure `N8N_BASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `CLIPCRAFT_DATA_DIR` from `backend/.env.example`.

The backend calls the existing WF02, WF10, and WF11 webhook contracts. Media endpoints serve only `final.mp4` and `thumbnail.jpg` from the UUID-scoped job directory. WF15 is intentionally not used for media delivery.
