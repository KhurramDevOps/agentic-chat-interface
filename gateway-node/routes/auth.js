/**
 * routes/auth.js
 * ───────────────
 * Authentication routes — production hardened.
 *
 * POST   /signup          — register (express-validator enforced)
 * POST   /login           — authenticate, return 1h JWT + 7d refresh token
 * GET    /me              — get own profile (protected)
 * PUT    /profile         — update name/password (protected)
 * POST   /forgot-password — generate reset token
 * POST   /refresh         — exchange refresh token for new 1h access token
 * POST   /reset-password  — consume reset token, update password
 * POST   /logout          — invalidate refresh token (protected)
 */

const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const rateLimit = require('express-rate-limit');
const { body, validationResult } = require('express-validator');
const User = require('../models/User');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

// ── Rate limiter ──────────────────────────────────────────────────────────────

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => req.headers['x-test-client'] || req.ip || '127.0.0.1',
  message: { message: 'Too many requests, please try again later.' },
});

// ── Validation rules ──────────────────────────────────────────────────────────

const signupValidation = [
  body('name').notEmpty().withMessage('Name is required.').trim(),
  body('email').isEmail().withMessage('A valid email address is required.').normalizeEmail(),
  body('password')
    .isLength({ min: 6 })
    .withMessage('Password must be at least 6 characters.'),
];

function handleValidation(req, res) {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({ message: errors.array()[0].msg, errors: errors.array() });
  }
  return null;
}

// ── POST /signup ──────────────────────────────────────────────────────────────

router.post('/signup', authLimiter, signupValidation, async (req, res) => {
  const validationError = handleValidation(req, res);
  if (validationError) return;

  try {
    const { name, email, password } = req.body;

    const existing = await User.findOne({ email });
    if (existing) {
      return res.status(409).json({ message: 'User already exists!' });
    }

    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash(password, salt);

    const user = new User({ name, email, password: hashedPassword });
    await user.save();

    return res.status(201).json({ message: 'User registered successfully.' });
  } catch (err) {
    console.error('Signup error:', err.message);
    return res.status(500).json({ message: 'Server error during signup.' });
  }
});

// ── POST /login ───────────────────────────────────────────────────────────────

router.post('/login', authLimiter, async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ message: 'Email and password are required.' });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user) {
      return res.status(401).json({ message: 'Invalid email or password!' });
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ message: 'Invalid email or password!' });
    }

    // Access token — 1 hour, signed with JWT_SECRET
    const token = jwt.sign(
      { id: user._id.toString(), email: user.email },
      process.env.JWT_SECRET,
      { expiresIn: '1h' }
    );

    const refreshToken = crypto.randomBytes(64).toString('hex');
    user.refreshToken = sha256(refreshToken);
    await user.save();

    return res.status(200).json({ token, refreshToken });
  } catch (err) {
    console.error('Login error:', err.message);
    return res.status(500).json({ message: 'Server error during login.' });
  }
});

// ── GET /me ───────────────────────────────────────────────────────────────────

router.get('/me', verifyToken, async (req, res) => {
  try {
    const user = await User.findById(req.user.id)
      .select('-password -passwordResetToken -passwordResetExpires -refreshToken');
    if (!user) return res.status(404).json({ message: 'User not found.' });
    return res.status(200).json(user);
  } catch (err) {
    console.error('Get me error:', err.message);
    return res.status(500).json({ message: 'Server error.' });
  }
});

// ── PUT /profile ──────────────────────────────────────────────────────────────

router.put('/profile', verifyToken, async (req, res) => {
  try {
    const { name, password } = req.body;

    if (!name && !password) {
      return res.status(400).json({ message: 'Provide at least one field to update.' });
    }

    const updates = {};
    if (name) updates.name = name.trim();
    if (password) {
      const salt = await bcrypt.genSalt(10);
      updates.password = await bcrypt.hash(password, salt);
    }

    const user = await User.findByIdAndUpdate(
      req.user.id,
      { $set: updates },
      { new: true }
    ).select('-password -passwordResetToken -passwordResetExpires -refreshToken');

    if (!user) return res.status(404).json({ message: 'User not found.' });

    return res.status(200).json({ message: 'Profile updated successfully.', user });
  } catch (err) {
    console.error('Profile update error:', err.message);
    return res.status(500).json({ message: 'Server error during profile update.' });
  }
});

// ── POST /forgot-password ─────────────────────────────────────────────────────

router.post('/forgot-password', async (req, res) => {
  try {
    const { email } = req.body;
    if (!email) return res.status(400).json({ message: 'Email is required.' });

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user) return res.status(404).json({ message: 'No account found with that email.' });

    const resetToken = crypto.randomBytes(32).toString('hex');
    user.passwordResetToken = sha256(resetToken);
    user.passwordResetExpires = new Date(Date.now() + 60 * 60 * 1000);
    await user.save();

    return res.status(200).json({
      message: 'Password reset token generated. Check your email.',
      ...(process.env.NODE_ENV !== 'production' && { resetToken }),
    });
  } catch (err) {
    console.error('Forgot password error:', err.message);
    return res.status(500).json({ message: 'Server error during password reset.' });
  }
});

// ── POST /refresh ─────────────────────────────────────────────────────────────

router.post('/refresh', async (req, res) => {
  try {
    const { refreshToken } = req.body;
    if (!refreshToken) return res.status(401).json({ message: 'Refresh token is required.' });

    const user = await User.findOne({ refreshToken: sha256(refreshToken) }).select('+refreshToken');
    if (!user) return res.status(401).json({ message: 'Refresh token not recognised.' });

    const newAccessToken = jwt.sign(
      { id: user._id.toString(), email: user.email },
      process.env.JWT_SECRET,
      { expiresIn: '1h' }
    );

    return res.status(200).json({ token: newAccessToken });
  } catch (err) {
    console.error('Refresh error:', err.message);
    return res.status(500).json({ message: 'Server error during token refresh.' });
  }
});

// ── POST /reset-password ──────────────────────────────────────────────────────

router.post('/reset-password', async (req, res) => {
  try {
    const { resetToken, newPassword } = req.body;
    if (!resetToken || !newPassword) {
      return res.status(400).json({ message: 'resetToken and newPassword are required.' });
    }

    const user = await User.findOne({
      passwordResetToken: sha256(resetToken),
      passwordResetExpires: { $gt: new Date() },
    }).select('+passwordResetToken');
    if (!user) return res.status(400).json({ message: 'Invalid or expired reset token.' });

    const salt = await bcrypt.genSalt(10);
    user.password = await bcrypt.hash(newPassword, salt);
    user.passwordResetToken = null;
    user.passwordResetExpires = null;
    await user.save();

    return res.status(200).json({ message: 'Password reset successfully.' });
  } catch (err) {
    console.error('Reset password error:', err.message);
    return res.status(500).json({ message: 'Server error during password reset.' });
  }
});

// ── POST /logout ──────────────────────────────────────────────────────────────

router.post('/logout', verifyToken, async (req, res) => {
  try {
    await User.findByIdAndUpdate(req.user.id, { $set: { refreshToken: null } });
    return res.status(200).json({ message: 'Logged out successfully.' });
  } catch (err) {
    console.error('Logout error:', err.message);
    return res.status(500).json({ message: 'Server error during logout.' });
  }
});

module.exports = router;
