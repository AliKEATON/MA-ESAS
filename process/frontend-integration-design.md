# Frontend Integration Module Design

## Goals
1. Align `frontend-streamlit/` with the current backend API contracts.
2. Support real login, conversation list, conversation creation, and unified message sending.
3. Show task progress, task result, failure state, and retry actions in Streamlit.
4. Remove outdated frontend entry logic and old API usage without breaking the repository layout.

## Scope
- Follow `docs/1-5` as the source of truth.
- Use only `POST /api/conversations/{conversation_id}/messages` for user input.
- Read task progress from `GET /api/analysis/tasks/{task_id}`.
- Read task results from `GET /api/analysis/tasks/{task_id}/result`.
- This module does not add new backend business logic.

## Atomic Work Items
1. Replace the old frontend API client with one that matches the current auth, conversation, and task routes.
2. Rebuild Streamlit state management around login state, selected conversation, messages, and task caches.
3. Implement the main chat view with conversation list, message flow, and unified send action.
4. Add task progress, result display, failure notice, and retry entry.
5. Clean old placeholders and complete module-level self-checks.

## Key Files
- `frontend-streamlit/app.py`
- `frontend-streamlit/utils/api_client.py`
- `backend/app/api/conversations.py`
- `backend/app/api/analysis.py`

## Notes
- Keep frontend state in `st.session_state`.
- Prefer compatibility fixes over extra abstraction.
- Land the main flow first, then fill in rename, delete, and retry actions.
