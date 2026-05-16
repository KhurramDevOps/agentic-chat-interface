import React from 'react';
import { Container, Row, Col } from 'react-bootstrap';
import Sidebar from './Sidebar';
import MessageList from './MessageList';
import InputArea from './InputArea';
import useChatStore from '../../store/chatStore';
import '../../styles/Chat.css';

/**
 * ChatLayout
 * ───────────
 * Bootstrap grid shell.
 * col-md-3 → Sidebar
 * col-md-9 → Message panel + Input area
 *
 * Receives sendMessage from ChatPage (via useWebSocket hook).
 */
function ChatLayout({ sendMessage }) {
  const activeSessionId = useChatStore((s) => s.activeSessionId);

  return (
    <Container fluid className="chat-container">
      <Row className="chat-row">

        {/* Sidebar */}
        <Col md={3} className="chat-sidebar-col p-0">
          <Sidebar />
        </Col>

        {/* Main panel */}
        <Col md={9} className="chat-main-col p-0">
          <div className="chat-main">

            {activeSessionId ? (
              <>
                <div className="chat-messages-wrap">
                  <MessageList />
                </div>
                <div className="chat-input-wrap">
                  <InputArea sendMessage={sendMessage} sessionId={activeSessionId} />
                </div>
              </>
            ) : (
              <div className="chat-empty-state">
                <p>Select a session or start a new chat.</p>
              </div>
            )}

          </div>
        </Col>

      </Row>
    </Container>
  );
}

export default ChatLayout;
