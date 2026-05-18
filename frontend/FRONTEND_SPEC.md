# Frontend Technical Specification — Phase 1 (MVP)
## Agentic AI Platform — React Frontend

**Version:** 1.0.0
**Status:** Active
**Stack:** React (CRA) · Bootstrap · External CSS · React Router · Zustand · Axios · WebSocket

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Directory Structure](#2-directory-structure)
3. [Component Hierarchy](#3-component-hierarchy)
4. [State Management Plan](#4-state-management-plan)
5. [API Integration Points](#5-api-integration-points)
6. [Step-by-Step Implementation Guide](#6-step-by-step-implementation-guide)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend (CRA)                     │
│                                                             │
│  AuthPortal ──► Zustand AuthStore ──► apiClient (Axios)     │
│  ChatLayout ──► Zustand ChatStore ──► WebSocket connection  │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTPS / WSS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Node.js API Gateway  (:3001)                    │
│                                                             │
│  POST /api/auth/login          JWT (1h) + refreshToken (7d) │
│  POST /api/auth/signup         User registration            │
│  POST /api/auth/refresh        Rotate access token          │
│  POST /api/auth/logout         Invalidate refresh token     │
│  GET  /api/auth/me             Authenticated user profile   │
│  POST /api/chat/stream         SSE proxy → Python engine    │
│  GET  /api/history/:sessionId  Conversation history         │
│  GET  /api/usage               Token usage stats            │
└──────────────────────────┬──────────────────────────────────┘
                           │  Internal HTTP / WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           Python AI Engine (FastAPI  :8000)                  │
│                                                             │
│  WS  /api/v1/stream/ws/{client_id}   Real-time token stream │
│  Multi-agent swarm · Groq/Gemini switching · Token metering │
└─────────────────────────────────────────────────────────────┘
```

### Communication Rules

| Channel | Used For | Auth |
|---|---|---|
| Axios (REST) | Auth, history, usage | `Authorization: Bearer <token>` |
| WebSocket (WSS) | Real-time AI token streaming | `client_id` in URL path |
| Gateway SSE proxy | Alternative streaming path | `Authorization: Bearer <token>` |

> **Decision:** The frontend connects to the **Node.js Gateway only**. It never calls the Python engine directly. The Gateway proxies all AI traffic and injects `X-User-ID` and `X-API-Key` headers before forwarding.

---

## 2. Directory Structure

```
frontend/src/
│
├── api/
│   ├── apiClient.js          # Axios instance with interceptors
│   ├── authApi.js            # login, signup, refresh, logout, me
│   ├── chatApi.js            # non-streaming completions
│   └── historyApi.js         # history, usage
│
├── components/
│   ├── auth/
│   │   ├── AuthCard.jsx
│   │   ├── AuthForm.jsx
│   │   ├── AuthHeader.jsx
│   │   └── AuthToggle.jsx
│   │
│   ├── chat/
│   │   ├── ChatLayout.jsx    # root chat page shell
│   │   ├── Sidebar.jsx       # session list + new chat button
│   │   ├── MessageList.jsx   # scrollable message history
│   │   ├── MessageBubble.jsx # single user/assistant message
│   │   ├── InputArea.jsx     # textarea + send button
│   │   └── StreamingDot.jsx  # animated "AI is typing" indicator
│   │
│   └── shared/
│       ├── ProtectedRoute.jsx  # redirects unauthenticated users
│       ├── LoadingSpinner.jsx
│       └── ErrorBanner.jsx
│
├── hooks/
│   ├── useAuth.js            # thin wrapper over AuthStore
│   ├── useChat.js            # thin wrapper over ChatStore
│   └── useWebSocket.js       # WebSocket lifecycle management
│
├── pages/
│   ├── AuthPortal.jsx        # login/register page
│   └── ChatPage.jsx          # main chat page
│
├── store/
│   ├── authStore.js          # Zustand — user, token, refresh logic
│   └── chatStore.js          # Zustand — sessions, messages, streaming state
│
├── styles/
│   ├── AuthPortal.css
│   ├── ChatLayout.css
│   ├── MessageBubble.css
│   ├── Sidebar.css
│   └── InputArea.css
│
├── utils/
│   └── tokenUtils.js         # decode JWT, check expiry
│
├── App.js                    # Router + ProtectedRoute wiring
└── index.js                  # Bootstrap + CSS imports, ReactDOM.render
```

---

## 3. Component Hierarchy

```
App
├── AuthPortal  (public route: /login)
│   ├── AuthCard
│   │   ├── AuthHeader
│   │   ├── AuthForm
│   │   └── AuthToggle
│
└── ChatPage  (protected route: /chat)
    └── ChatLayout
        ├── Sidebar
        │   ├── [SessionItem × N]
        │   └── NewChatButton
        │
        └── main panel
            ├── MessageList
            │   └── MessageBubble × N
            │       └── StreamingDot  (visible only on last assistant bubble while streaming)
            └── InputArea
```

### Component Responsibilities

| Component | Responsibility |
|---|---|
| `App` | Declares routes, wraps with `ProtectedRoute` |
| `AuthPortal` | Owns login/register state, calls `authStore` actions |
| `AuthForm` | Controlled form fields, emits `onSubmit` |
| `ChatPage` | Initialises WebSocket on mount, tears down on unmount |
| `ChatLayout` | Bootstrap grid shell — sidebar + main panel |
| `Sidebar` | Renders session list from `chatStore`, triggers new session |
| `MessageList` | Reads `messages` from `chatStore`, auto-scrolls to bottom |
| `MessageBubble` | Renders a single message; handles `role` (user/assistant) styling |
| `StreamingDot` | Animated indicator shown while `chatStore.isStreaming === true` |
| `InputArea` | Controlled textarea, dispatches message to `chatStore` |
| `ProtectedRoute` | Reads `authStore.token`; redirects to `/login` if null |

---

## 4. State Management Plan

### Why Zustand over Context API

Context API re-renders every consumer on every state change. For a chat interface with high-frequency streaming token updates (potentially 20–50 state updates per second), this causes severe performance degradation. Zustand uses a subscription model — only components that select the specific slice of state that changed re-render.

---

### 4.1 Auth Store (`store/authStore.js`)

```js
// Shape
{
  user: null,           // { id, name, email }
  token: null,          // access token — in memory only, never localStorage
  refreshToken: null,   // stored in localStorage (7-day expiry)
  isLoading: false,
  error: null,

  // Actions
  login(email, password)  → sets token + refreshToken + user
  signup(name, email, password) → calls /api/auth/signup, then login
  logout()                → calls /api/auth/logout, clears all state
  refreshAccessToken()    → calls /api/auth/refresh, updates token in memory
  fetchMe()               → calls /api/auth/me, populates user
}
```

**JWT Storage Strategy:**

| Token | Storage | Reason |
|---|---|---|
| Access token (1h) | Zustand in-memory only | Never persisted — XSS cannot steal it |
| Refresh token (7d) | `localStorage` | Survives page refresh; acceptable risk given HttpOnly cookie is not available in this stack |

**Refresh Token Flow:**

```
Axios request interceptor
  └── Attach: Authorization: Bearer <token>

Axios response interceptor (401 handler)
  └── Call authStore.refreshAccessToken()
        └── POST /api/auth/refresh  { refreshToken }
              ├── Success → update token in memory → retry original request
              └── Failure → authStore.logout() → redirect to /login
```

This is implemented once in `api/apiClient.js` and applies to every Axios call automatically.

---

### 4.2 Chat Store (`store/chatStore.js`)

```js
// Shape
{
  sessions: [],           // [{ id, title, createdAt }]
  activeSessionId: null,
  messages: [],           // [{ id, role, content, timestamp }]
  isStreaming: false,     // true while WebSocket is receiving tokens
  streamingContent: '',   // accumulates token deltas during streaming
  error: null,

  // Actions
  setActiveSession(sessionId)
  addMessage(role, content)
  appendStreamingToken(delta)   // called on every WS token event
  finaliseStream()              // moves streamingContent → messages, resets
  clearSession(sessionId)
  loadHistory(sessionId)        // fetches from /api/history/:sessionId
}
```

**Streaming State Machine:**

```
User sends message
  └── addMessage('user', content)
  └── isStreaming = true, streamingContent = ''
  └── WebSocket sends payload

WebSocket receives event:
  ├── type: 'status'    → (optional) show status text in UI
  ├── type: 'token'     → appendStreamingToken(event.delta)
  │                         └── MessageList re-renders last bubble with new content
  ├── type: 'complete'  → finaliseStream()
  │                         └── isStreaming = false
  │                         └── push { role: 'assistant', content: streamingContent } to messages
  │                         └── streamingContent = ''
  └── type: 'error'     → set error, isStreaming = false
```

---

### 4.3 WebSocket Hook (`hooks/useWebSocket.js`)

```js
// Manages the WebSocket lifecycle for the active chat session
useWebSocket(sessionId)
  ├── Opens:  wss://gateway/api/v1/stream/ws/{sessionId}  on mount
  ├── Routes incoming events to chatStore actions
  ├── Exposes: sendMessage(payload) function
  └── Closes connection on unmount or session change
```

The hook is called once inside `ChatPage`. `InputArea` calls `sendMessage` via a prop or context — it does not manage the socket itself.

---

## 5. API Integration Points

All requests go through `api/apiClient.js` — a configured Axios instance with base URL and interceptors.

```js
// api/apiClient.js
const apiClient = axios.create({
  baseURL: process.env.REACT_APP_GATEWAY_URL || 'http://localhost:3001',
  timeout: 30000,
});
```

---

### 5.1 Auth Endpoints

#### `POST /api/auth/signup`
```json
// Request
{ "name": "Alice", "email": "alice@example.com", "password": "secret123" }

// Response 201
{ "message": "User registered successfully." }

// Response 409
{ "message": "User already exists!" }
```

#### `POST /api/auth/login`
```json
// Request
{ "email": "alice@example.com", "password": "secret123" }

// Response 200
{ "token": "<jwt_access_1h>", "refreshToken": "<jwt_refresh_7d>" }

// Response 401
{ "message": "Invalid email or password!" }
```

#### `POST /api/auth/refresh`
```json
// Request
{ "refreshToken": "<jwt_refresh_7d>" }

// Response 200
{ "token": "<new_jwt_access_1h>" }

// Response 401
{ "message": "Invalid or expired refresh token." }
```

#### `POST /api/auth/logout`
```
// Header: Authorization: Bearer <token>
// Response 200
{ "message": "Logged out successfully." }
```

#### `GET /api/auth/me`
```
// Header: Authorization: Bearer <token>
// Response 200
{ "_id": "...", "name": "Alice", "email": "alice@example.com", "createdAt": "..." }
```

---

### 5.2 Chat — WebSocket Streaming

```
Connection: wss://<gateway>/api/v1/stream/ws/{client_id}
```

> **Note:** The Gateway's `/api/chat/stream` SSE endpoint is available as a fallback. The primary path for Phase 1 is the WebSocket endpoint on the Python engine, accessed via the Gateway's proxy.

**Outbound message (client → server):**
```json
{
  "request_id": "uuid-v4",
  "messages": [
    { "role": "user", "content": "Explain quantum entanglement." }
  ],
  "model": "gemini/gemini-1.5-pro",
  "memory_context_id": "<session_id>"
}
```

**Inbound events (server → client):**
```json
// Status event
{ "event_type": "status", "request_id": "...", "sequence": 0, "message": "Processing your message..." }

// Token event (fires N times)
{ "event_type": "token", "request_id": "...", "sequence": 1, "delta": "Quantum " }
{ "event_type": "token", "request_id": "...", "sequence": 2, "delta": "entanglement " }

// Complete event
{ "event_type": "complete", "request_id": "...", "sequence": 42 }

// Error event
{ "event_type": "error", "request_id": "...", "sequence": 1, "message": "Agent error: ..." }
```

---

### 5.3 History & Usage Endpoints

#### `GET /api/history/:sessionId`
```
// Header: Authorization: Bearer <token>
// Response 200
{
  "session_id": "...",
  "messages": [
    { "role": "user", "content": "Hello", "timestamp": "..." },
    { "role": "assistant", "content": "Hi there!", "timestamp": "..." }
  ]
}
```

#### `DELETE /api/history/:sessionId`
```
// Header: Authorization: Bearer <token>
// Response 200
{ "message": "History cleared." }
```

#### `GET /api/usage`
```
// Header: Authorization: Bearer <token>
// Response 200
{ "user_id": "...", "total_tokens": 14200, "requests": 38 }
```

---

## 6. Step-by-Step Implementation Guide

### Phase 1A — Foundation & Auth (Week 1)

- [ ] **1.** Confirm CRA project runs (`npm start`). Verify Bootstrap, react-bootstrap, react-router-dom, zustand, axios are installed.
- [ ] **2.** Create `src/api/apiClient.js` — Axios instance with `baseURL` from `REACT_APP_GATEWAY_URL`. Add request interceptor to attach `Authorization: Bearer <token>` from `authStore`. Add response interceptor to handle 401 → call `refreshAccessToken()` → retry.
- [ ] **3.** Create `src/api/authApi.js` — export `login()`, `signup()`, `logout()`, `fetchMe()`, `refresh()` functions that call `apiClient`.
- [ ] **4.** Create `src/store/authStore.js` — Zustand store with shape defined in Section 4.1. Implement `login`, `signup`, `logout`, `refreshAccessToken`, `fetchMe` actions. Store `refreshToken` in `localStorage` on login; clear on logout.
- [ ] **5.** Create `src/hooks/useAuth.js` — thin selector hook over `authStore`.
- [ ] **6.** Create `src/components/shared/ProtectedRoute.jsx` — reads `authStore.token`; renders `<Outlet />` if present, redirects to `/login` otherwise.
- [ ] **7.** Wire `App.js` with React Router: `/login` → `AuthPortal`, `/chat` → `ChatPage` wrapped in `ProtectedRoute`. Add a root redirect from `/` to `/login`.
- [ ] **8.** Update `AuthForm.jsx` to call `authStore.login()` or `authStore.signup()` on submit. Show `authStore.error` in `ErrorBanner`. Show `LoadingSpinner` while `authStore.isLoading`.
- [ ] **9.** Test: register a new user, log in, verify JWT is in Zustand memory, verify redirect to `/chat`.
- [ ] **10.** Test: refresh the page — `refreshToken` from `localStorage` should silently re-issue an access token via the interceptor on the first protected API call.

---

### Phase 1B — Chat Store & WebSocket (Week 2)

- [ ] **11.** Create `src/store/chatStore.js` — Zustand store with shape defined in Section 4.2. Implement all actions.
- [ ] **12.** Create `src/hooks/useWebSocket.js` — opens `wss://<gateway>/api/v1/stream/ws/{sessionId}` on mount. On each incoming message, parse JSON and route to the correct `chatStore` action (`appendStreamingToken`, `finaliseStream`, etc.). Return `sendMessage(payload)`. Close socket on unmount.
- [ ] **13.** Create `src/api/historyApi.js` — export `getHistory(sessionId)`, `deleteHistory(sessionId)`, `getUsage()`.
- [ ] **14.** Create `src/pages/ChatPage.jsx` — calls `useWebSocket(activeSessionId)`. On mount, calls `chatStore.loadHistory(activeSessionId)`. Renders `ChatLayout`.
- [ ] **15.** Create `src/components/chat/ChatLayout.jsx` — Bootstrap `Container` with a `Row`: `Col md={3}` for `Sidebar`, `Col md={9}` for message panel + input.
- [ ] **16.** Create `src/components/chat/Sidebar.jsx` — reads `chatStore.sessions`. Renders a list of session items. "New Chat" button generates a UUID session ID and calls `chatStore.setActiveSession`.
- [ ] **17.** Create `src/components/chat/MessageList.jsx` — reads `chatStore.messages` and `chatStore.streamingContent`. Maps messages to `MessageBubble`. Appends a streaming bubble with `streamingContent` when `isStreaming === true`. Auto-scrolls to bottom using a `useEffect` + `ref`.
- [ ] **18.** Create `src/components/chat/MessageBubble.jsx` — accepts `{ role, content }` props. Applies `.bubble-user` or `.bubble-assistant` CSS class. Renders `StreamingDot` when `isStreaming` and it is the last bubble.
- [ ] **19.** Create `src/components/chat/StreamingDot.jsx` — three animated dots indicating the AI is typing. Pure CSS animation.
- [ ] **20.** Create `src/components/chat/InputArea.jsx` — controlled `<textarea>`. On Enter (without Shift) or button click: calls `chatStore.addMessage('user', content)`, then calls `sendMessage(payload)` from `useWebSocket`. Clears input. Disables while `chatStore.isStreaming === true`.

---

### Phase 1C — Polish, Error Handling & Deployment Prep (Week 3)

- [ ] **21.** Create `src/components/shared/ErrorBanner.jsx` — dismissible error display. Used in both `AuthPortal` and `ChatPage`.
- [ ] **22.** Create `src/components/shared/LoadingSpinner.jsx` — Bootstrap spinner, used during auth and history loading.
- [ ] **23.** Add `src/utils/tokenUtils.js` — `decodeToken(token)` and `isTokenExpired(token)` using `atob` on the JWT payload. Used by the Axios interceptor to proactively refresh before expiry rather than waiting for a 401.
- [ ] **24.** Handle WebSocket reconnection — in `useWebSocket`, implement exponential backoff reconnect (max 5 attempts) when the socket closes unexpectedly.
- [ ] **25.** Add `src/styles/` CSS files for each component. Ensure all dark-theme colours, input focus states, bubble alignment, and sidebar styles are defined in external CSS only.
- [ ] **26.** Create `.env` file: `REACT_APP_GATEWAY_URL=http://localhost:3001`. Create `.env.production` with the deployed gateway URL.
- [ ] **27.** Add `REACT_APP_GATEWAY_URL` to `.gitignore` exclusions if it contains secrets. Commit `.env.example` with placeholder values.
- [ ] **28.** Run `npm run build`. Verify the production bundle has no console errors. Test the full flow: register → login → send message → receive streamed response → refresh page → session persists.

---

## Appendix — Environment Variables

```bash
# .env
REACT_APP_GATEWAY_URL=http://localhost:3001
REACT_APP_WS_URL=ws://localhost:3001
```

## Appendix — Key Decisions Log

| Decision | Rationale |
|---|---|
| Zustand over Context API | Avoids full re-render tree on every streaming token update |
| Access token in memory | Eliminates XSS token theft via `localStorage` |
| Refresh token in `localStorage` | No HttpOnly cookie available; acceptable for this stack |
| WebSocket over SSE | Python engine exposes a WebSocket endpoint natively; bidirectional protocol allows future features (cancel generation, ping) |
| Bootstrap for layout only | Avoids Bootstrap's opinionated component styles conflicting with custom dark theme |
| External CSS only | Keeps JSX clean and styling auditable in one place per component |
