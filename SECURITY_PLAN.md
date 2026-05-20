# Auth Integration Plan — Keycloak + JWT

## Goal

Secure all backend endpoints with Keycloak-issued JWTs. Sessions are scoped per
user: each user can only see and access their own sessions and history.

---

## Architecture overview

```
Browser (keycloak-js)
  │  login → Keycloak (port 8080)
  │  receive access_token
  │
  ├─ GET /sessions          Authorization: Bearer <token>
  ├─ POST /chat             Authorization: Bearer <token>
  └─ ...all endpoints...

FastAPI backend
  │  validate JWT via Keycloak JWKS endpoint (RS256, no introspection call)
  │  extract sub + preferred_username from claims
  └─ scope DB/Redis queries to user_id = sub

MCP microservices (8002, 8003, 8004)
  └─ no change — internal Docker network only, never exposed publicly
```

---

## Phase 1 — Keycloak in docker-compose

### 1.1 Add Keycloak service

Add to `docker-compose.yml`:

```yaml
keycloak:
  image: quay.io/keycloak/keycloak:24.0
  command: start-dev --import-realm
  ports:
    - "8080:8080"
  environment:
    KC_DB: dev-mem # in-memory for local dev; swap to postgres for prod
    KEYCLOAK_ADMIN: ${KC_ADMIN:-admin}
    KEYCLOAK_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD:-admin}
    KC_HOSTNAME_STRICT: "false"
    KC_HTTP_ENABLED: "true"
  volumes:
    - ./keycloak/realm-export.json:/opt/keycloak/data/import/realm-export.json
  healthcheck:
    test:
      ["CMD-SHELL", "curl -sf http://localhost:8080/realms/master || exit 1"]
    interval: 15s
    timeout: 10s
    retries: 10
    start_period: 30s
```

Add `keycloak` as a dependency for `backend` (condition: `service_healthy`).

### 1.2 Realm bootstrap file

Create `keycloak/realm-export.json` that configures:

- **Realm**: `multi-tool-chat`
- **Client**: `frontend`
  - Public client (no secret needed in browser)
  - Standard flow + Direct access grants enabled
  - Valid redirect URIs: `http://localhost:5173/*`
  - Web origins: `http://localhost:5173`
- **Test user**: `testuser / testpass` (for local dev)

This file is imported automatically by `--import-realm` on first start.

### 1.3 New env vars (`.env.example`)

```
KC_ADMIN=admin
KC_ADMIN_PASSWORD=admin
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=multi-tool-chat
KEYCLOAK_CLIENT_ID=frontend
```

---

## Phase 2 — Backend JWT validation

### 2.1 New config fields (`app/config.py`)

```python
keycloak_url: str = "http://localhost:8080"
keycloak_realm: str = "multi-tool-chat"
keycloak_client_id: str = "frontend"

@property
def keycloak_jwks_url(self) -> str:
    return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

@property
def keycloak_issuer(self) -> str:
    return f"{self.keycloak_url}/realms/{self.keycloak_realm}"
```

### 2.2 Auth module (`app/auth/`)

**`app/auth/jwt.py`** — JWT validation dependency:

- On startup (or first request), fetch JWKS from Keycloak and cache the public keys
  with a 5-minute TTL (refresh on key-not-found to handle key rotation).
- Validate the `Authorization: Bearer <token>` header using `python-jose` or `authlib`.
- Verify: signature (RS256), `iss` matches `keycloak_issuer`, `aud` or `azp` matches
  `keycloak_client_id`, token not expired.
- Return a `CurrentUser(sub: str, username: str)` dataclass on success.
- Raise `HTTP 401` on missing/invalid token.

**`app/auth/__init__.py`** — exports `get_current_user` FastAPI dependency.

### 2.3 Protect routes (`app/api/routes.py`)

Add `current_user: CurrentUser = Depends(get_current_user)` to every endpoint
**except** `/health` and `/config` (those stay public).

Endpoints to protect:

- `GET /sessions`
- `POST /sessions`
- `DELETE /sessions`
- `GET /sessions/{session_id}/messages`
- `POST /chat`
- `POST /upload_url`
- `DELETE /cache`

### 2.4 CORS update (`app/main.py`)

Add `http://localhost:8080` to `allow_origins` so Keycloak redirect flows work.
Also allow the bearer token header: `allow_headers=["*"]` (already set).

---

## Phase 3 — User-scoped sessions

### 3.1 Session model (`app/session/models.py`)

Add `user_id: str` field to `SessionRecord`.

### 3.2 Session store (`app/session/store.py` + `manager.py`)

- `create_session(session_id, title, user_id)` — store `user_id` alongside the record.
- `list_sessions(user_id)` — filter to return only sessions belonging to `user_id`.
- `ensure_session(session_id, message, user_id)` — pass through on creation.

Redis key strategy: sessions are currently stored under a flat key. Add the user's
`sub` as metadata in the session hash. `list_sessions` filters by `user_id` field
after retrieving all session keys (or use a per-user index set
`user:{user_id}:sessions` for O(1) listing — preferred if the session count grows).

### 3.3 Route wiring

Pass `current_user.sub` into every session store call that creates or lists sessions.
For `GET /sessions/{session_id}/messages` and `DELETE /sessions`, verify the session
belongs to `current_user.sub` before proceeding; return `HTTP 403` if not.

---

## Phase 4 — Frontend (keycloak-js)

### 4.1 Install

```bash
cd frontend
npm install keycloak-js
```

### 4.2 Keycloak initialization (`src/keycloak.ts`)

```ts
import Keycloak from "keycloak-js";

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "multi-tool-chat",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "frontend",
});
```

### 4.3 Bootstrap (`src/main.tsx`)

Initialize Keycloak with `onLoad: "login-required"` before mounting React.
If init fails, show an error screen rather than mounting an unauthenticated app.

```ts
keycloak.init({ onLoad: "login-required", checkLoginIframe: false }).then((auth) => {
  if (auth) {
    // Mount React
    createRoot(...).render(<App />);
    // Refresh token 30 seconds before expiry
    setInterval(() => keycloak.updateToken(30), 60_000);
  }
});
```

### 4.4 Authenticated fetch helper (`src/api.ts`)

Centralise all API calls through a thin wrapper that automatically attaches the token:

```ts
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  await keycloak.updateToken(10); // refresh if expiring in < 10 s
  return fetch(path, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${keycloak.token}`,
    },
  });
}
```

Replace every bare `fetch(...)` call in `App.tsx` with `apiFetch(...)`.

### 4.5 Header — user info + logout

Update `Header.tsx` to show `keycloak.tokenParsed?.preferred_username` and a
**Logout** button that calls `keycloak.logout()`.

### 4.6 New env vars (`.env` / Vite)

```
VITE_KEYCLOAK_URL=http://localhost:8080
VITE_KEYCLOAK_REALM=multi-tool-chat
VITE_KEYCLOAK_CLIENT_ID=frontend
```

---

## Phase 5 — Docker wiring

Update `docker-compose.yml` `backend` environment block:

```yaml
KEYCLOAK_URL: http://keycloak:8080 # internal Docker hostname
KEYCLOAK_REALM: multi-tool-chat
KEYCLOAK_CLIENT_ID: frontend
```

Update `frontend` environment block with `VITE_*` vars pointing to
`http://localhost:8080` (browser-facing, not internal).

Update `CORS_ORIGINS` on the backend to also include the Keycloak origin if needed.

---

## Dependency additions

### Backend (`backend/3rdparty/requirements.txt`)

```
python-jose[cryptography]>=3.3      # JWT validation + JWKS
httpx>=0.27                         # async JWKS fetch (already likely present)
```

### Frontend (`frontend/package.json`)

```
keycloak-js ^24.0
```

---

## Implementation order

| Step | What                                           | Risk                                    |
| ---- | ---------------------------------------------- | --------------------------------------- |
| 1    | Add Keycloak to docker-compose + realm JSON    | Low — additive only                     |
| 2    | Backend auth module + JWKS validation          | Medium — new dependency                 |
| 3    | Protect routes (no session scoping yet)        | Medium — breaks unauthenticated callers |
| 4    | Session model + store user_id scoping          | Medium — data model change              |
| 5    | Frontend keycloak-js + apiFetch wrapper        | Low — UI layer only                     |
| 6    | Wire VITE env vars + docker-compose env        | Low — config only                       |
| 7    | End-to-end smoke test (login → chat → history) | —                                       |

---

## What is NOT in scope

- Keycloak in production mode (TLS, external DB) — this plan targets local dev.
- Role-based access control (RBAC) beyond "authenticated = full access".
- MCP microservice token propagation — internal network, no public exposure.
- Social login / SSO with external IdPs.
