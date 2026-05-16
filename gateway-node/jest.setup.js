// Set default environment variables for all test suites
// Individual test files may override these with their own values.
process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-default';
process.env.PYTHON_API_KEY = process.env.PYTHON_API_KEY || 'test-python-api-key';
process.env.PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000/api/v1/chat/completions';
