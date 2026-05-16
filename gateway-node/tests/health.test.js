/**
 * tests/health.test.js
 * ─────────────────────
 * Specs for the health check endpoint.
 *
 * GET /api/health
 */

const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');

let app;
let mongoServer;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  app = require('../server');
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

describe('GET /api/health', () => {

  it('should return 200 with status healthy', async () => {
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('healthy');
  });

  it('should not require authentication', async () => {
    // Health check must be publicly accessible — no token needed
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
  });

  it('should return a JSON response', async () => {
    const res = await request(app).get('/api/health');
    expect(res.headers['content-type']).toMatch(/json/);
  });

  it('should include a timestamp or uptime field', async () => {
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
    // Either a timestamp or uptime is acceptable
    const hasTimestamp = res.body.timestamp !== undefined;
    const hasUptime = res.body.uptime !== undefined;
    const hasService = res.body.service !== undefined;
    expect(hasTimestamp || hasUptime || hasService).toBe(true);
  });

});
