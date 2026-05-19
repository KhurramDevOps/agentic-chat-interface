const express = require('express');
const User = require('../models/User');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

function userIdFromReq(req) {
  return String(req.user.userId || req.user.id);
}

function publicMemory(user) {
  const memory = user.memory || {};
  return {
    name: memory.name || '',
    nickname: memory.nickname || '',
    occupation: memory.occupation || '',
    location: memory.location || '',
    facts: Array.isArray(memory.facts) ? memory.facts.filter(Boolean) : [],
    interests: Array.isArray(user.onboarding?.interests) ? user.onboarding.interests : [],
    responseStyle: user.onboarding?.responseStyle || '',
    memoryEnabled: user.onboarding?.memoryEnabled !== false,
    webSearchEnabled: user.onboarding?.webSearchEnabled !== false,
    lastUpdated: memory.lastUpdated || null,
  };
}

router.post('/onboarding', verifyToken, async (req, res) => {
  try {
    const user = await User.findById(userIdFromReq(req));
    if (!user) return res.status(404).json({ message: 'User not found.' });

    const {
      name,
      nickname = '',
      occupation = '',
      location = '',
      interests = [],
      responseStyle = 'casual',
      memoryEnabled = true,
      webSearchEnabled = true,
    } = req.body || {};

    if (name && typeof name === 'string') user.name = name.trim();
    user.memory = {
      ...(user.memory || {}),
      name: (name || user.memory?.name || user.name || '').trim(),
      nickname: String(nickname || '').trim(),
      occupation: String(occupation || '').trim(),
      location: String(location || '').trim(),
      facts: Array.isArray(user.memory?.facts) ? user.memory.facts : [],
      lastUpdated: new Date(),
    };
    user.onboarding = {
      completed: true,
      interests: Array.isArray(interests) ? interests.map(String).slice(0, 20) : [],
      responseStyle,
      memoryEnabled: Boolean(memoryEnabled),
      webSearchEnabled: Boolean(webSearchEnabled),
      completedAt: new Date(),
    };
    user.onboardingComplete = true;

    await user.save();
    return res.status(200).json({
      user: {
        id: user._id.toString(),
        name: user.name,
        email: user.email,
        onboardingComplete: true,
        onboardingCompleted: true,
      },
      memory: publicMemory(user),
    });
  } catch (err) {
    console.error('Onboarding error:', err.message);
    return res.status(500).json({ message: 'Failed to save onboarding.' });
  }
});

router.get('/memory', verifyToken, async (req, res) => {
  try {
    const user = await User.findById(userIdFromReq(req));
    if (!user) return res.status(404).json({ message: 'User not found.' });
    return res.status(200).json({ memory: publicMemory(user) });
  } catch (err) {
    console.error('User memory error:', err.message);
    return res.status(500).json({ message: 'Failed to load memory.' });
  }
});

router.delete('/memory/:factId', verifyToken, async (req, res) => {
  try {
    const user = await User.findById(userIdFromReq(req));
    if (!user) return res.status(404).json({ message: 'User not found.' });

    const facts = Array.isArray(user.memory?.facts) ? [...user.memory.facts] : [];
    const index = Number.parseInt(req.params.factId, 10);
    const decodedFact = decodeURIComponent(req.params.factId);

    let nextFacts;
    if (Number.isInteger(index) && index >= 0 && index < facts.length) {
      nextFacts = facts.filter((_, factIndex) => factIndex !== index);
    } else {
      nextFacts = facts.filter((fact) => fact !== decodedFact);
    }

    user.memory = {
      ...(user.memory || {}),
      facts: nextFacts,
      lastUpdated: new Date(),
    };
    await user.save();

    return res.status(200).json({ memory: publicMemory(user) });
  } catch (err) {
    console.error('Delete memory fact error:', err.message);
    return res.status(500).json({ message: 'Failed to delete memory fact.' });
  }
});

module.exports = router;
