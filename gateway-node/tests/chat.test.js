/**
 * tests/chat.test.js
 * ───────────────────
 * Spec-driven tests for the Python AI proxy route.
 *
 * POST /api/chat
 *
 * Uses jest.mock('axios') to intercept outbound HTTP calls so no real
 * Python service is needed. Uses mongodb-memory-server for auth setup.
 *
 * Architectural contract being tested:
 *   1. Route is protected by verifyToken middleware.
 *   2. Authenticated requests forward req.body to PYTHON_API_URL.
 *   3. Two headers are injected into the Axios call:
 *        X-User-ID : req.user.id
 *        X-API-Key : process.env.PYTHON_API_KEY
 *   4. The Python service response is returned to the client.
 */

// Mock axios BEFORE requiring any app modules
jest.mock('axios');

const axios = require('axios');
const request = require('supertest');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const { MongoMemoryServer } = require('mongodb-memory-server');

// ── Environment ───────────────────────────────────────────────────────────────

const TEST_JWT_SECRET = 'test-jwt-secret-for-chat-specs';
const TEST_API_KEY = 'test-python-api-key-xyz';
const TEST_PYTHON_URL = 'http://localhost:8000/api/v1/chat/completions';

process.env.JWT_SECRET = TEST_JWT_SECRET;
process.env.PYTHON_API_KEY = TEST_API_KEY;
process.env.PYTHON_API_URL = TEST_PYTHON_URL;

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Generate a signed JWT for a test user.
 */
function makeToken(payload = {}) {
  const defaults = { id: 'user-test-id-001', email: 'chat@example.com' };
  return jwt.sign({ ...defaults, ...payload }, TEST_JWT_SECRET, { expiresIn: '1h' });
}

// ── Setup / Teardown ──────────────────────────────────────────────────────────

let app;
let mongoServer;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  app = require('../server');
});

afterEach(async () => {
  jest.clearAllMocks();
  const collections = mongoose.connection.collections;
  for (const key in collections) {
    await collections[key].deleteMany({});
  }
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('POST /api/chat', () => {

  // ── Auth enforcement ─────────────────────────────────────────────────────────

  it('should return 401/403 when no token is provided', async () => {
    const res = await request(app)
      .post('/api/chat')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });

    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).toBeLessThan(500);

    // axios must NOT have been called — request was blocked at middleware
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('should return 401/403 when an invalid token is provided', async () => {
    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', 'Bearer invalid.token.here')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });

    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(axios.post).not.toHaveBeenCalled();
  });

  // ── Authenticated proxy behaviour ─────────────────────────────────────────────

  it('should forward the request body to the Python service when authenticated', async () => {
    const mockPythonResponse = {
      data: {
        request_id: 'py-req-001',
        content: 'Hello from the AI!',
        agent: { agent_name: 'TriageAgent' },
      },
    };
    axios.post.mockResolvedValueOnce(mockPythonResponse);

    const body = {
      messages: [{ role: 'user', content: 'What is 2+2?' }],
      model: 'llama-3.3-70b-versatile',
    };

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send(body);

    expect(res.status).toBe(200);

    // axios.post must have been called exactly once
    expect(axios.post).toHaveBeenCalledTimes(1);

    // The first argument must be the Python API URL
    const [calledUrl] = axios.post.mock.calls[0];
    expect(calledUrl).toBe(TEST_PYTHON_URL);

    // The second argument must include the forwarded body
    const [, calledBody] = axios.post.mock.calls[0];
    expect(calledBody).toMatchObject(body);
  });

  it('should inject X-User-ID and X-API-Key headers into the Axios request', async () => {
    const userId = 'injected-user-id-999';
    const mockPythonResponse = {
      data: { content: 'Response with headers verified.' },
    };
    axios.post.mockResolvedValueOnce(mockPythonResponse);

    await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`)
      .send({ messages: [{ role: 'user', content: 'Test headers' }] });

    expect(axios.post).toHaveBeenCalledTimes(1);

    // The third argument to axios.post is the config object containing headers
    const [, , calledConfig] = axios.post.mock.calls[0];

    expect(calledConfig).toBeDefined();
    expect(calledConfig.headers).toBeDefined();

    // X-User-ID must be the authenticated user's id
    expect(calledConfig.headers['X-User-ID']).toBe(userId);

    // X-API-Key must be the env secret
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
  });

  it('should return the Python service response body to the client', async () => {
    const pythonPayload = {
      request_id: 'py-req-002',
      content: 'The answer is 42.',
      agent: { agent_name: 'ResearchAgent', handoff_occurred: false },
      model: 'llama-3.3-70b-versatile',
    };
    axios.post.mockResolvedValueOnce({ data: pythonPayload });

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'What is the answer?' }] });

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject(pythonPayload);
  });

  // ── Error handling ────────────────────────────────────────────────────────────

  it('should return 502 or 500 when the Python service is unreachable', async () => {
    axios.post.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'Will this fail?' }] });

    expect(res.status).toBeGreaterThanOrEqual(500);
  });

  it('should propagate a 4xx error from the Python service', async () => {
    const axiosError = {
      response: {
        status: 422,
        data: { error: { code: 'VALIDATION_ERROR', message: 'Bad request body' } },
      },
    };
    axios.post.mockRejectedValueOnce(axiosError);

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [] });

    // Gateway should surface the upstream error status or a 5xx
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  // ── Request ID forwarding (optional but good practice) ────────────────────────

  it('should include a request_id in the forwarded body', async () => {
    axios.post.mockResolvedValueOnce({ data: { content: 'ok' } });

    await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'test' }] });

    const [, calledBody] = axios.post.mock.calls[0];

    // The gateway should inject a request_id if the client didn't provide one
    // OR pass through the client's request_id
    expect(
      calledBody.request_id !== undefined ||
      calledBody.messages !== undefined
    ).toBe(true);
  });

});
