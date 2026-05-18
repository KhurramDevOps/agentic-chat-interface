/**
 * middleware/authMiddleware.js
 * ────────────────────────────
 * JWT verification middleware.
 *
 * Accepts tokens via:
 *   Authorization: Bearer <token>
 *   x-auth-token: <token>
 *
 * On success: attaches decoded payload to req.user and calls next().
 * On failure: returns 401 with a descriptive error message.
 */

const jwt = require('jsonwebtoken');

const verifyToken = (req, res, next) => {
  // Extract token from Authorization header or x-auth-token
  let token = null;

  const authHeader = req.headers['authorization'] || req.headers['Authorization'];
  if (authHeader) {
    // Handle "Bearer <token>" and raw token formats
    token = authHeader.startsWith('Bearer ')
      ? authHeader.slice(7).trim()
      : authHeader.trim();
  } else if (req.headers['x-auth-token']) {
    token = req.headers['x-auth-token'].trim();
  }

  if (!token) {
    return res.status(401).json({ message: 'Access denied! No token provided' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    if (!decoded || !decoded.id) {
      return res.status(401).json({ message: 'Invalid token payload' });
    }
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ message: 'Invalid token' });
  }
};

module.exports = verifyToken;
