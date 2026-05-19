const express = require('express');
const ChatSession = require('../models/ChatSession');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

function userIdFromReq(req) {
  return String(req.user.userId || req.user.id);
}

router.post('/:id/reaction', verifyToken, async (req, res) => {
  try {
    const reaction = req.body?.reaction;
    if (!['up', 'down', null].includes(reaction)) {
      return res.status(400).json({ message: 'reaction must be up, down, or null.' });
    }

    const session = await ChatSession.findOne({
      userId: userIdFromReq(req),
      'messages._id': req.params.id,
    });

    if (!session) return res.status(404).json({ message: 'Message not found.' });

    const message = session.messages.id(req.params.id);
    if (!message) return res.status(404).json({ message: 'Message not found.' });
    message.reaction = reaction;
    await session.save();

    return res.status(200).json({ messageId: req.params.id, reaction });
  } catch (err) {
    console.error('Reaction error:', err.message);
    return res.status(500).json({ message: 'Failed to save reaction.' });
  }
});

module.exports = router;
