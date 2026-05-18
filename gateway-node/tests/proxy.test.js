/**
 * tests/proxy.test.js
 * ────────────────────
 * Specs for the history and usage proxy routes.
 *
 * GET    /api/history/:sessionId   — proxy to Python history endpoint
 * DELETE /api/history/:sessionId   — proxy to Python delete history
 * GET    /api/usage                — proxy to Python usage endpoint
 *
 * All routes must:
 *   - Enforce verifyToken middleware
 *   - Inject X-User-ID, X-API-Key, X-Request-ID into upstream headers
 *   - Forward the response from the Python service to the client
 */

jest.mock('axios');

const axios = require('axios');
const request = require('supertest');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const { MongoMemoryServer } = require('mongodb-memory-server');

const TEST_JWT_SECRET = 'test-jwt-secret-for-proxy-specs';
const TEST_API_KEY = 'test-python-api-key-proxy';
const TEST_PYTHON_BASE = 'http://localhost:8000/api/v1';

process.env.JWT_SECRET = TEST_JWT_SECRET;
process.env.PYTHON_API_KEY = TEST_API_KEY;
process.env.PYTHON_BASE_URL = TEST_PYTHON_BASE;

function makeToken(payload = {}) {
  const defaults = { id: 'proxy-user-id-001', email: 'proxy@example.com' };
  return jwt.sign({ ...defaults, ...payload }, TEST_JWT_SECRET, { expiresIn: '1h' });
}

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

// ── GET /api/history/:sessionId ───────────────────────────────────────────────

describe('GET /api/history/:sessionId', () => {

  it('should return 401 when no token is provided', async () => {
    const res = await request(app).get('/api/history/session-abc');
    expect(res.status).toBe(401);
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('should return 401 for an invalid token', async () => {
    const res = await request(app)
      .get('/api/history/session-abc')
      .set('Authorization', 'Bearer bad.token');
    expect(res.status).toBe(401);
  });

  it('should proxy to the Python history endpoint and return the response', async () => {
    const mockHistory = [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there!' },
    ];
    axios.get.mockResolvedValueOnce({ data: mockHistory });

    const res = await request(app)
      .get('/api/history/my-session-123')
      .set('Authorization', `Bearer ${makeToken()}`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(mockHistory);
    expect(axios.get).toHaveBeenCalledTimes(1);

    const [calledUrl] = axios.get.mock.calls[0];
    expect(calledUrl).toContain('my-session-123');
  });

  it('should inject X-User-ID and X-API-Key headers into the upstream request', async () => {
    const userId = 'history-user-id-555';
    axios.get.mockResolvedValueOnce({ data: [] });

    await request(app)
      .get('/api/history/sess-xyz')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`);

    const [, calledConfig] = axios.get.mock.calls[0];
    expect(calledConfig.headers['X-User-ID']).toBe(userId);
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
  });

  it('should inject an X-Request-ID header into the upstream request', async () => {
    axios.get.mockResolvedValueOnce({ data: [] });

    await request(app)
      .get('/api/history/sess-req-id')
      .set('Authorization', `Bearer ${makeToken()}`);

    const [, calledConfig] = axios.get.mock.calls[0];
    expect(calledConfig.headers['X-Request-ID']).toBeDefined();
    expect(typeof calledConfig.headers['X-Request-ID']).toBe('string');
    expect(calledConfig.headers['X-Request-ID'].length).toBeGreaterThan(0);
  });

  it('should propagate a client-supplied X-Request-ID', async () => {
    const clientRequestId = 'client-req-id-abc-123';
    axios.get.mockResolvedValueOnce({ data: [] });

    await request(app)
      .get('/api/history/sess-propagate')
      .set('Authorization', `Bearer ${makeToken()}`)
      .set('X-Request-ID', clientRequestId);

    const [, calledConfig] = axios.get.mock.calls[0];
    expect(calledConfig.headers['X-Request-ID']).toBe(clientRequestId);
  });

  it('should return 502 when the Python service is unreachable', async () => {
    axios.get.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await request(app)
      .get('/api/history/sess-fail')
      .set('Authorization', `Bearer ${makeToken()}`);

    expect(res.status).toBeGreaterThanOrEqual(500);
  });

});

// ── DELETE /api/history/:sessionId ────────────────────────────────────────────

describe('DELETE /api/history/:sessionId', () => {

  it('should return 401 when no token is provided', async () => {
    const res = await request(app).delete('/api/history/session-abc');
    expect(res.status).toBe(401);
    expect(axios.delete).not.toHaveBeenCalled();
  });

  it('should proxy the delete to the Python service', async () => {
    axios.delete.mockResolvedValueOnce({ data: { message: 'History cleared.' } });

    const res = await request(app)
      .delete('/api/history/del-session-456')
      .set('Authorization', `Bearer ${makeToken()}`);

    expect(res.status).toBe(200);
    expect(axios.delete).toHaveBeenCalledTimes(1);

    const [calledUrl] = axios.delete.mock.calls[0];
    expect(calledUrl).toContain('del-session-456');
  });

  it('should inject X-User-ID, X-API-Key, and X-Request-ID headers', async () => {
    const userId = 'delete-user-id-888';
    axios.delete.mockResolvedValueOnce({ data: {} });

    await request(app)
      .delete('/api/history/del-sess')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`);

    const [, calledConfig] = axios.delete.mock.calls[0];
    expect(calledConfig.headers['X-User-ID']).toBe(userId);
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
    expect(calledConfig.headers['X-Request-ID']).toBeDefined();
  });

});

// ── GET /api/usage ────────────────────────────────────────────────────────────

describe('GET /api/usage', () => {

  it('should return 401 when no token is provided', async () => {
    const res = await request(app).get('/api/usage');
    expect(res.status).toBe(401);
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('should proxy to the Python usage endpoint using req.user.id', async () => {
    const userId = 'usage-user-id-999';
    const mockUsage = {
      user_id: `anon_${userId}`,
      total_tokens_used: 1500,
      prompt_tokens: 900,
      completion_tokens: 600,
    };
    axios.get.mockResolvedValueOnce({ data: mockUsage });

    const res = await request(app)
      .get('/api/usage')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`);

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject(mockUsage);
    expect(axios.get).toHaveBeenCalledTimes(1);

    // URL must include the user's ID
    const [calledUrl] = axios.get.mock.calls[0];
    expect(calledUrl).toContain(userId);
  });

  it('should inject X-User-ID, X-API-Key, and X-Request-ID headers', async () => {
    const userId = 'usage-header-user';
    axios.get.mockResolvedValueOnce({ data: { total_tokens_used: 0 } });

    await request(app)
      .get('/api/usage')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`);

    const [, calledConfig] = axios.get.mock.calls[0];
    expect(calledConfig.headers['X-User-ID']).toBe(userId);
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
    expect(calledConfig.headers['X-Request-ID']).toBeDefined();
  });

  it('should return 502 when the Python service is unreachable', async () => {
    axios.get.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await request(app)
      .get('/api/usage')
      .set('Authorization', `Bearer ${makeToken()}`);

    expect(res.status).toBeGreaterThanOrEqual(500);
  });

});
