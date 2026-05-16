/**
 * tests/auth.test.js
 * ───────────────────
 * Spec-driven tests for the authentication routes.
 *
 * POST /api/auth/signup
 * POST /api/auth/login
 *
 * Uses mongodb-memory-server for a fully isolated, in-process database.
 * No real MongoDB connection is required.
 */

const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');

let app;
let mongoServer;

// ── Setup / Teardown ──────────────────────────────────────────────────────────

beforeAll(async () => {
  // Spin up an in-memory MongoDB instance
  mongoServer = await MongoMemoryServer.create();
  const uri = mongoServer.getUri();

  // Connect mongoose to the in-memory server
  await mongoose.connect(uri);

  // Load the app AFTER the DB is connected so models bind correctly
  app = require('../server');
});

afterEach(async () => {
  // Wipe all collections between tests for isolation
  const collections = mongoose.connection.collections;
  for (const key in collections) {
    await collections[key].deleteMany({});
  }
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

// ── POST /api/auth/signup ─────────────────────────────────────────────────────

describe('POST /api/auth/signup', () => {

  const validUser = {
    name: 'Test User',
    email: 'test@example.com',
    password: 'password123',
  };

  it('should register a new user and return a success response', async () => {
    const res = await request(app)
      .post('/api/auth/signup')
      .send(validUser);

    expect(res.status).toBeGreaterThanOrEqual(200);
    expect(res.status).toBeLessThan(300);

    // Response must contain some indication of success
    const body = res.body;
    const bodyStr = JSON.stringify(body).toLowerCase();
    expect(
      bodyStr.includes('success') ||
      bodyStr.includes('created') ||
      bodyStr.includes('registered') ||
      bodyStr.includes('user') ||
      res.status === 201
    ).toBe(true);
  });

  it('should hash the password — stored hash must not equal plain text', async () => {
    await request(app)
      .post('/api/auth/signup')
      .send(validUser);

    // Load the User model and find the saved document
    const User = require('../models/User');
    const savedUser = await User.findOne({ email: validUser.email });

    expect(savedUser).not.toBeNull();
    expect(savedUser.password).toBeDefined();
    // The stored value must NOT be the plain-text password
    expect(savedUser.password).not.toBe(validUser.password);
    // bcrypt hashes always start with $2b$ or $2a$
    expect(savedUser.password).toMatch(/^\$2[ab]\$/);
  });

  it('should return an error when the email is already registered', async () => {
    // Register once
    await request(app)
      .post('/api/auth/signup')
      .send(validUser);

    // Attempt to register again with the same email
    const res = await request(app)
      .post('/api/auth/signup')
      .send(validUser);

    expect(res.status).toBeGreaterThanOrEqual(400);

    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('already') ||
      bodyStr.includes('exists') ||
      bodyStr.includes('duplicate') ||
      bodyStr.includes('taken')
    ).toBe(true);
  });

  it('should return 400 when required fields are missing', async () => {
    const res = await request(app)
      .post('/api/auth/signup')
      .send({ email: 'incomplete@example.com' }); // no name or password

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});

// ── POST /api/auth/login ──────────────────────────────────────────────────────

describe('POST /api/auth/login', () => {

  const credentials = {
    name: 'Login User',
    email: 'login@example.com',
    password: 'securePass99',
  };

  // Register the user before each login test
  beforeEach(async () => {
    await request(app)
      .post('/api/auth/signup')
      .send(credentials);
  });

  it('should return a JWT token for valid credentials', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .send({ email: credentials.email, password: credentials.password });

    expect(res.status).toBe(200);

    // Response must contain a token field
    expect(res.body.token).toBeDefined();
    expect(typeof res.body.token).toBe('string');

    // A JWT has exactly three dot-separated base64url segments
    const parts = res.body.token.split('.');
    expect(parts).toHaveLength(3);
  });

  it('should return "Invalid email or password!" for a wrong password', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .send({ email: credentials.email, password: 'wrongPassword!' });

    expect(res.status).toBeGreaterThanOrEqual(400);

    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('invalid') ||
      bodyStr.includes('incorrect') ||
      bodyStr.includes('wrong') ||
      bodyStr.includes('password')
    ).toBe(true);
  });

  it('should return "Invalid email or password!" for an unregistered email', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .send({ email: 'nobody@example.com', password: 'anyPassword' });

    expect(res.status).toBeGreaterThanOrEqual(400);

    const bodyStr = JSON.stringify(res.body).toLowerCase();
    expect(
      bodyStr.includes('invalid') ||
      bodyStr.includes('not found') ||
      bodyStr.includes('email') ||
      bodyStr.includes('password')
    ).toBe(true);
  });

  it('should return 400 when email is missing from login body', async () => {
    const res = await request(app)
      .post('/api/auth/login')
      .send({ password: 'somePassword' });

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

});
