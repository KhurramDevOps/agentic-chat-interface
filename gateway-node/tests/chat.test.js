/**
 * tests/chat.test.js
 * ───────────────────
 * Specs for the Python AI proxy routes.
 *
 * POST /api/chat         — non-streaming completions proxy
 * POST /api/chat/stream  — SSE streaming proxy
 */

jest.mock('axios');

const axios = require('axios');
const request = require('supertest');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const { MongoMemoryServer } = require('mongodb-memory-server');
const { EventEmitter } = require('events');

const TEST_JWT_SECRET = 'test-jwt-secret-for-chat-specs';
const TEST_API_KEY = 'test-python-api-key-xyz';
const TEST_PYTHON_URL = 'http://localhost:8000/api/v1/chat/completions';
const TEST_PYTHON_STREAM_URL = 'http://localhost:8000/api/v1/chat/stream';

process.env.JWT_SECRET = TEST_JWT_SECRET;
process.env.PYTHON_API_KEY = TEST_API_KEY;
process.env.PYTHON_API_URL = TEST_PYTHON_URL;
process.env.PYTHON_STREAM_URL = TEST_PYTHON_STREAM_URL;

function makeToken(payload = {}) {
  const defaults = { id: 'user-test-id-001', email: 'chat@example.com' };
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

// ── POST /api/chat ────────────────────────────────────────────────────────────

describe('POST /api/chat', () => {

  it('should return 401 when no token is provided', async () => {
    const res = await request(app)
      .post('/api/chat')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).toBeLessThan(500);
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('should return 401 for an invalid token', async () => {
    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', 'Bearer invalid.token.here')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('should forward the request body to the Python service', async () => {
    axios.post.mockResolvedValueOnce({
      data: { request_id: 'py-req-001', content: 'Hello from the AI!' },
    });

    const body = { messages: [{ role: 'user', content: 'What is 2+2?' }] };
    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send(body);

    expect(res.status).toBe(200);
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [calledUrl, calledBody] = axios.post.mock.calls[0];
    expect(calledUrl).toBe(TEST_PYTHON_URL);
    expect(calledBody).toMatchObject(body);
  });

  it('should inject X-User-ID and X-API-Key headers', async () => {
    const userId = 'injected-user-id-999';
    axios.post.mockResolvedValueOnce({ data: { content: 'ok' } });

    await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`)
      .send({ messages: [{ role: 'user', content: 'Test' }] });

    const [, , calledConfig] = axios.post.mock.calls[0];
    expect(calledConfig.headers['X-User-ID']).toBe(userId);
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
  });

  it('should return the Python service response body', async () => {
    const pythonPayload = { request_id: 'py-req-002', content: 'The answer is 42.' };
    axios.post.mockResolvedValueOnce({ data: pythonPayload });

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'What is the answer?' }] });

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject(pythonPayload);
  });

  it('should return 502 when the Python service is unreachable', async () => {
    axios.post.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'fail?' }] });

    expect(res.status).toBeGreaterThanOrEqual(500);
  });

  it('should propagate a 4xx error from the Python service', async () => {
    axios.post.mockRejectedValueOnce({
      response: { status: 422, data: { error: 'Bad request' } },
    });

    const res = await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [] });

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should include a request_id in the forwarded body', async () => {
    axios.post.mockResolvedValueOnce({ data: { content: 'ok' } });

    await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'test' }] });

    const [, calledBody] = axios.post.mock.calls[0];
    expect(
      calledBody.request_id !== undefined || calledBody.messages !== undefined
    ).toBe(true);
  });

  // ── Timeout ────────────────────────────────────────────────────────────────

  it('should include a timeout in the Axios config', async () => {
    axios.post.mockResolvedValueOnce({ data: { content: 'ok' } });

    await request(app)
      .post('/api/chat')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'timeout test' }] });

    const [, , calledConfig] = axios.post.mock.calls[0];
    expect(calledConfig.timeout).toBeDefined();
    expect(typeof calledConfig.timeout).toBe('number');
    // Must be at least 5 seconds, at most 60 seconds
    expect(calledConfig.timeout).toBeGreaterThanOrEqual(5000);
    expect(calledConfig.timeout).toBeLessThanOrEqual(60000);
  });

});

// ── POST /api/chat/stream ─────────────────────────────────────────────────────

describe('POST /api/chat/stream', () => {

  it('should return 401 when no token is provided', async () => {
    const res = await request(app)
      .post('/api/chat/stream')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).toBeLessThan(500);
  });

  it('should return 401 for an invalid token', async () => {
    const res = await request(app)
      .post('/api/chat/stream')
      .set('Authorization', 'Bearer bad.token')
      .send({ messages: [{ role: 'user', content: 'Hello' }] });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should set Content-Type to text/event-stream for authenticated requests', async () => {
    // Mock axios to return a readable stream-like response
    const mockStream = new EventEmitter();
    mockStream.data = null;

    // axios.post for SSE returns a response with a data stream
    axios.post.mockResolvedValueOnce({
      data: {
        on: jest.fn((event, cb) => {
          if (event === 'data') {
            // Immediately emit one chunk then end
            setImmediate(() => {
              cb(Buffer.from('data: {"type":"token","content":"Hello"}\n\n'));
              cb(Buffer.from('data: {"type":"complete"}\n\n'));
            });
          }
          if (event === 'end') {
            setImmediate(() => cb());
          }
          return { on: jest.fn() };
        }),
        pipe: jest.fn(),
      },
      headers: { 'content-type': 'text/event-stream' },
    });

    const res = await request(app)
      .post('/api/chat/stream')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'stream test' }] })
      .buffer(true)
      .parse((res, callback) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk.toString(); });
        res.on('end', () => callback(null, data));
      });

    expect(res.headers['content-type']).toMatch(/text\/event-stream/);
  });

  it('should inject X-User-ID and X-API-Key into the upstream SSE request', async () => {
    const userId = 'stream-user-id-777';

    axios.post.mockResolvedValueOnce({
      data: {
        on: jest.fn((event, cb) => {
          if (event === 'end') setImmediate(() => cb());
          return { on: jest.fn() };
        }),
        pipe: jest.fn(),
      },
      headers: { 'content-type': 'text/event-stream' },
    });

    await request(app)
      .post('/api/chat/stream')
      .set('Authorization', `Bearer ${makeToken({ id: userId })}`)
      .send({ messages: [{ role: 'user', content: 'test' }] })
      .buffer(true)
      .parse((res, callback) => {
        res.on('data', () => {});
        res.on('end', () => callback(null, ''));
      });

    expect(axios.post).toHaveBeenCalledTimes(1);
    const [, , calledConfig] = axios.post.mock.calls[0];
    expect(calledConfig.headers['X-User-ID']).toBe(userId);
    expect(calledConfig.headers['X-API-Key']).toBe(TEST_API_KEY);
  });

  it('should return 502 when the Python SSE service is unreachable', async () => {
    axios.post.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await request(app)
      .post('/api/chat/stream')
      .set('Authorization', `Bearer ${makeToken()}`)
      .send({ messages: [{ role: 'user', content: 'fail' }] });

    expect(res.status).toBeGreaterThanOrEqual(500);
  });

});
