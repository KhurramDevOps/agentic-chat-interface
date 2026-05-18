// Set default environment variables for all test suites
jest.setTimeout(30000);

process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-default';
process.env.JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || 'test-jwt-refresh-secret-default';
process.env.PYTHON_API_KEY = process.env.PYTHON_API_KEY || 'test-python-api-key';
process.env.PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000/api/v1/chat/completions';
process.env.PYTHON_STREAM_URL = process.env.PYTHON_STREAM_URL || 'http://localhost:8000/api/v1/chat/stream';
process.env.PYTHON_BASE_URL = process.env.PYTHON_BASE_URL || 'http://localhost:8000';
