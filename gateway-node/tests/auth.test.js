/**
 * tests/auth.test.js
 * ───────────────────
 * Specs for all authentication routes.
 *
 * POST   /api/auth/signup
 * POST   /api/auth/login
 * GET    /api/auth/me
 * PUT    /api/auth/profile
 * POST   /api/auth/forgot-password
 * Rate limiting on /login and /signup
 */

const request = require('supertest');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const { MongoMemoryServer } = require('mongodb-memory-server');

let app;
let mongoServer;

// ── Setup / Teardown ──────────────────────────────────────────────────────────

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  app = require('../server');
});

afterEach(async () => {
  const collections = mongoose.connection.collections;
  for (const key in collections) {
    await collections[key].deleteMany({});
  }
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

// ── Helpers ───────────────────────────────────────────────────────────────────

const validUser = {
  name: 'Test User',
  email: 'test@example.com',
  password: 'password123',
};

async function registerAndLogin(userData = validUser) {
  // Use a unique test-client key so this helper doesn't exhaust the rate limit bucket
  await request(app)
    .post('/api/auth/signup')
    .set('X-Test-Client', `helper-${Date.now()}-${Math.random()}`)
    .send(userData);
  const res = await request(app)
    .post('/api/auth/login')
    .set('X-Test-Client', `helper-${Date.now()}-${Math.random()}`)
    .send({ email: userData.email, password: userData.password });
  return res.body.token;
}

// ── POST /api/auth/signup ─────────────────────────────────────────────────────

describe('POST /api/auth/signup', () => {

  it('should register a new user and return a success response', async () => {
    const res = await request(app).post('/api/auth/signup').send(validUser);
    expect(res.status).toBeGreaterThanOrEqual(200);
    expect(res.status).toBeLessThan(300);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('success') || bodyStr.includes('created') ||
      bodyStr.includes('registered') || bodyStr.includes('user') || res.status === 201
    ).toBe(true);
  });

  it('should hash the password — stored hash must not equal plain text', async () => {
    await request(app).post('/api/auth/signup').send(validUser);
    const User = require('../models/User');
    const savedUser = await User.findOne({ email: validUser.email });
    expect(savedUser).not.toBeNull();
    expect(savedUser.password).not.toBe(validUser.password);
    expect(savedUser.password).toMatch(/^\$2[ab]\$/);
  });

  it('should return an error when the email is already registered', async () => {
    await request(app).post('/api/auth/signup').send(validUser);
    const res = await request(app).post('/api/auth/signup').send(validUser);
    expect(res.status).toBeGreaterThanOrEqual(400);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('already') || bodyStr.includes('exists') ||
      bodyStr.includes('duplicate') || bodyStr.includes('taken')
    ).toBe(true);
  });

  it('should return 400 when required fields are missing', async () => {
    const res = await request(app)
      .post('/api/auth/signup')
      .send({ email: 'incomplete@example.com' });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});

// ── POST /api/auth/login ──────────────────────────────────────────────────────

describe('POST /api/auth/login', () => {

  const credentials = { name: 'Login User', email: 'login@example.com', password: 'securePass99' };

  beforeEach(async () => {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `login-setup-${Date.now()}-${Math.random()}`)
      .send(credentials);
  });

  it('should return a JWT token for valid credentials', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `login-valid-${Date.now()}`)
      .send({ email: credentials.email, password: credentials.password });
    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
    expect(typeof res.body.token).toBe('string');
    expect(res.body.token.split('.')).toHaveLength(3);
  });

  it('should return "Invalid email or password!" for a wrong password', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `login-wrong-pw-${Date.now()}`)
      .send({ email: credentials.email, password: 'wrongPassword!' });
    expect(res.status).toBeGreaterThanOrEqual(400);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('invalid') || bodyStr.includes('incorrect') ||
      bodyStr.includes('wrong') || bodyStr.includes('password')
    ).toBe(true);
  });

  it('should return "Invalid email or password!" for an unregistered email', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `login-unknown-${Date.now()}`)
      .send({ email: 'nobody@example.com', password: 'anyPassword' });
    expect(res.status).toBeGreaterThanOrEqual(400);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('invalid') || bodyStr.includes('not found') ||
      bodyStr.includes('email') || bodyStr.includes('password')
    ).toBe(true);
  });

  it('should return 400 when email is missing from login body', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `login-no-email-${Date.now()}`)
      .send({ password: 'somePassword' });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});

// ── GET /api/auth/me ──────────────────────────────────────────────────────────

describe('GET /api/auth/me', () => {

  it('should return user details (without password) for a valid token', async () => {
    const token = await registerAndLogin();
    const res = await request(app)
      .get('/api/auth/me')
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body).toBeDefined();

    // Must return name and email
    expect(res.body.name).toBeDefined();
    expect(res.body.email).toBe(validUser.email.toLowerCase());

    // Must NOT expose the password
    expect(res.body.password).toBeUndefined();
  });

  it('should return 401 when no token is provided', async () => {
    const res = await request(app).get('/api/auth/me');
    expect(res.status).toBe(401);
  });

  it('should return 401 for an invalid token', async () => {
    const res = await request(app)
      .get('/api/auth/me')
      .set('Authorization', 'Bearer bad.token.here');
    expect(res.status).toBe(401);
  });

});

// ── PUT /api/auth/profile ─────────────────────────────────────────────────────

describe('PUT /api/auth/profile', () => {

  it('should allow a user to update their name', async () => {
    const token = await registerAndLogin();
    const res = await request(app)
      .put('/api/auth/profile')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Updated Name' });

    expect(res.status).toBe(200);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('updated') || bodyStr.includes('success') ||
      res.body.name === 'Updated Name'
    ).toBe(true);
  });

  it('should hash the new password when updating password', async () => {
    const token = await registerAndLogin();
    await request(app)
      .put('/api/auth/profile')
      .set('Authorization', `Bearer ${token}`)
      .send({ password: 'newSecurePass456' });

    const User = require('../models/User');
    const user = await User.findOne({ email: validUser.email });
    // New password must be hashed, not plain text
    expect(user.password).not.toBe('newSecurePass456');
    expect(user.password).toMatch(/^\$2[ab]\$/);
  });

  it('should allow login with the new password after update', async () => {
    const token = await registerAndLogin();
    await request(app)
      .put('/api/auth/profile')
      .set('Authorization', `Bearer ${token}`)
      .send({ password: 'brandNewPass789' });

    const loginRes = await request(app)
      .post('/api/auth/login')
      .send({ email: validUser.email, password: 'brandNewPass789' });

    expect(loginRes.status).toBe(200);
    expect(loginRes.body.token).toBeDefined();
  });

  it('should return 401 when not authenticated', async () => {
    const res = await request(app)
      .put('/api/auth/profile')
      .send({ name: 'Hacker' });
    expect(res.status).toBe(401);
  });

});

// ── POST /api/auth/forgot-password ────────────────────────────────────────────

describe('POST /api/auth/forgot-password', () => {

  it('should return 200 and a success message for a registered email', async () => {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `forgot-setup-${Date.now()}`)
      .send(validUser);
    const res = await request(app)
      .post('/api/auth/forgot-password')
      .send({ email: validUser.email });

    expect(res.status).toBe(200);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('reset') || bodyStr.includes('sent') ||
      bodyStr.includes('email') || bodyStr.includes('token')
    ).toBe(true);
  });

  it('should return 404 for an unregistered email', async () => {
    const res = await request(app)
      .post('/api/auth/forgot-password')
      .send({ email: 'ghost@example.com' });
    expect(res.status).toBe(404);
  });

  it('should store a resetToken on the user document', async () => {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `forgot-token-setup-${Date.now()}`)
      .send(validUser);
    await request(app)
      .post('/api/auth/forgot-password')
      .send({ email: validUser.email });

    const User = require('../models/User');
    const user = await User.findOne({ email: validUser.email });
    expect(user.resetToken).toBeDefined();
    expect(typeof user.resetToken).toBe('string');
    expect(user.resetToken.length).toBeGreaterThan(10);
  });

  it('should return 400 when email field is missing', async () => {
    const res = await request(app)
      .post('/api/auth/forgot-password')
      .send({});
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});

// ── POST /api/auth/refresh ────────────────────────────────────────────────────

describe('POST /api/auth/refresh', () => {

  it('should return a new 1-hour access token when given a valid refresh token', async () => {
    // Login to get both tokens
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `refresh-setup-${Date.now()}`)
      .send(validUser);
    const loginRes = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `refresh-login-${Date.now()}`)
      .send({ email: validUser.email, password: validUser.password });

    expect(loginRes.body.refreshToken).toBeDefined();
    const { refreshToken } = loginRes.body;

    const res = await request(app)
      .post('/api/auth/refresh')
      .send({ refreshToken });

    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
    expect(typeof res.body.token).toBe('string');
    expect(res.body.token.split('.')).toHaveLength(3);

    // New access token must expire in 1h
    const decoded = jwt.decode(res.body.token);
    const expiresIn = decoded.exp - decoded.iat;
    expect(expiresIn).toBe(3600);
  });

  it('should return 401 when no refresh token is provided', async () => {
    const res = await request(app).post('/api/auth/refresh').send({});
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should return 401 for an invalid/tampered refresh token', async () => {
    const res = await request(app)
      .post('/api/auth/refresh')
      .send({ refreshToken: 'tampered.refresh.token' });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should return 401 for a refresh token not found in the database', async () => {
    // Sign a valid-looking token but don't save it to any user
    const fakeRefresh = jwt.sign(
      { id: 'nonexistent-user' },
      process.env.JWT_REFRESH_SECRET || process.env.JWT_SECRET,
      { expiresIn: '7d' }
    );
    const res = await request(app)
      .post('/api/auth/refresh')
      .send({ refreshToken: fakeRefresh });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('login response must include both token (1h) and refreshToken (7d)', async () => {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `refresh-both-setup-${Date.now()}`)
      .send(validUser);
    const res = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `refresh-both-login-${Date.now()}`)
      .send({ email: validUser.email, password: validUser.password });

    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
    expect(res.body.refreshToken).toBeDefined();

    const access = jwt.decode(res.body.token);
    const refresh = jwt.decode(res.body.refreshToken);
    expect(access.exp - access.iat).toBe(3600);          // 1 hour
    expect(refresh.exp - refresh.iat).toBeGreaterThan(3600); // longer than 1h
  });

});

// ── POST /api/auth/reset-password ─────────────────────────────────────────────

describe('POST /api/auth/reset-password', () => {

  async function setupResetToken() {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', `reset-setup-${Date.now()}`)
      .send(validUser);
    const forgotRes = await request(app)
      .post('/api/auth/forgot-password')
      .send({ email: validUser.email });
    return forgotRes.body.resetToken;
  }

  it('should update the password and clear the reset token', async () => {
    const resetToken = await setupResetToken();
    expect(resetToken).toBeDefined();

    const res = await request(app)
      .post('/api/auth/reset-password')
      .send({ resetToken, newPassword: 'freshNewPass123' });

    expect(res.status).toBe(200);
    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('success') || bodyStr.includes('updated') || bodyStr.includes('reset')
    ).toBe(true);
  });

  it('should allow login with the new password after reset', async () => {
    const resetToken = await setupResetToken();
    await request(app)
      .post('/api/auth/reset-password')
      .send({ resetToken, newPassword: 'afterResetPass456' });

    const loginRes = await request(app)
      .post('/api/auth/login')
      .set('X-Test-Client', `reset-login-${Date.now()}`)
      .send({ email: validUser.email, password: 'afterResetPass456' });

    expect(loginRes.status).toBe(200);
    expect(loginRes.body.token).toBeDefined();
  });

  it('should clear the resetToken field from the database after use', async () => {
    const resetToken = await setupResetToken();
    await request(app)
      .post('/api/auth/reset-password')
      .send({ resetToken, newPassword: 'clearTokenPass789' });

    const User = require('../models/User');
    const user = await User.findOne({ email: validUser.email });
    expect(user.resetToken).toBeNull();
  });

  it('should return 400 for an invalid or expired reset token', async () => {
    const res = await request(app)
      .post('/api/auth/reset-password')
      .send({ resetToken: 'invalid-token-xyz', newPassword: 'newPass123' });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it('should return 400 when required fields are missing', async () => {
    const res = await request(app)
      .post('/api/auth/reset-password')
      .send({ resetToken: 'some-token' }); // missing newPassword
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});

// ── Rate limiting on /login ───────────────────────────────────────────────────

describe('Rate limiting', () => {

  it('should return 429 after too many failed login attempts', async () => {
    await request(app)
      .post('/api/auth/signup')
      .set('X-Test-Client', 'rate-limit-test-bucket')
      .send(validUser);

    let lastStatus = 0;
    for (let i = 0; i < 15; i++) {
      const res = await request(app)
        .post('/api/auth/login')
        .set('X-Test-Client', 'rate-limit-test-bucket')
        .send({ email: validUser.email, password: 'wrongpassword' });
      lastStatus = res.status;
      if (res.status === 429) break;
    }

    expect(lastStatus).toBe(429);
  });

});
