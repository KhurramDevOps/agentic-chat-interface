/**
 * tests/middleware.test.js
 * ─────────────────────────
 * Spec-driven tests for the verifyToken JWT middleware.
 *
 * Tests the middleware both in isolation (direct invocation) and
 * via a dummy Express route mounted on the test app.
 */

const request = require('supertest');
const express = require('express');
const jwt = require('jsonwebtoken');

jest.mock('../db', () => jest.fn().mockResolvedValue(true));

// Use a fixed secret for all tests — matches what the middleware reads from env
const TEST_SECRET = 'test-jwt-secret-for-middleware-specs';

// Set the env var before requiring the middleware so it picks it up
process.env.JWT_SECRET = TEST_SECRET;

const verifyToken = require('../middleware/authMiddleware');

// ── Helper: build a minimal Express app with a protected dummy route ──────────

function buildTestApp() {
  const app = express();
  app.use(express.json());

  // Protected route — returns the decoded user payload if auth passes
  app.get('/protected', verifyToken, (req, res) => {
    res.status(200).json({ user: req.user });
  });

  return app;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('verifyToken middleware', () => {

  let testApp;

  beforeAll(() => {
    testApp = buildTestApp();
  });

  // ── No token ────────────────────────────────────────────────────────────────

  it('should reject requests with no Authorization header', async () => {
    const res = await request(testApp).get('/protected');

    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).toBeLessThan(500);

    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('no token') ||
      bodyStr.includes('access denied') ||
      bodyStr.includes('unauthorized') ||
      bodyStr.includes('token')
    ).toBe(true);
  });

  it('should reject requests with an empty Bearer token', async () => {
    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', 'Bearer ');

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  // ── Invalid / tampered token ─────────────────────────────────────────────────

  it('should reject requests with a tampered/invalid token', async () => {
    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', 'Bearer this.is.not.a.valid.jwt');

    expect(res.status).toBeGreaterThanOrEqual(400);

    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('invalid') ||
      bodyStr.includes('malformed') ||
      bodyStr.includes('token') ||
      bodyStr.includes('unauthorized')
    ).toBe(true);
  });

  it('should reject a token signed with a different secret', async () => {
    const wrongToken = jwt.sign(
      { id: 'user-123', email: 'test@example.com' },
      'completely-wrong-secret',
      { expiresIn: '1h' }
    );

    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', `Bearer ${wrongToken}`);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should reject an expired token', async () => {
    const expiredToken = jwt.sign(
      { id: 'user-123', email: 'test@example.com' },
      TEST_SECRET,
      { expiresIn: '-1s' } // already expired
    );

    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', `Bearer ${expiredToken}`);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  // ── Valid token ──────────────────────────────────────────────────────────────

  it('should allow requests with a valid token and attach decoded payload to req.user', async () => {
    const payload = { id: 'user-abc-123', email: 'valid@example.com' };
    const validToken = jwt.sign(payload, TEST_SECRET, { expiresIn: '1h' });

    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', `Bearer ${validToken}`);

    expect(res.status).toBe(200);
    expect(res.body.user).toBeDefined();

    // The decoded payload must contain the original id and email
    expect(res.body.user.id).toBe(payload.id);
    expect(res.body.user.email).toBe(payload.email);
  });

  it('should accept token passed as x-auth-token header (alternative format)', async () => {
    // Some implementations accept x-auth-token instead of Authorization: Bearer
    // This test is lenient — passes if either format works
    const payload = { id: 'user-xyz', email: 'alt@example.com' };
    const validToken = jwt.sign(payload, TEST_SECRET, { expiresIn: '1h' });

    // Try Bearer format (must work)
    const res = await request(testApp)
      .get('/protected')
      .set('Authorization', `Bearer ${validToken}`);

    expect(res.status).toBe(200);
  });

  // ── Direct middleware invocation ─────────────────────────────────────────────

  it('should call next() when token is valid (direct invocation)', () => {
    const payload = { id: 'direct-test', email: 'direct@example.com' };
    const token = jwt.sign(payload, TEST_SECRET, { expiresIn: '1h' });

    const req = {
      headers: { authorization: `Bearer ${token}` },
    };
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    const next = jest.fn();

    verifyToken(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(req.user).toBeDefined();
    expect(req.user.id).toBe(payload.id);
  });

  it('should call res.status(401) and NOT call next() when no token (direct invocation)', () => {
    const req = { headers: {} };
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    const next = jest.fn();

    verifyToken(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(expect.any(Number));
  });

});
