import React, { useContext } from 'react';
import ChatLayout from '../components/chat/ChatLayout';
import PageTitle from '../components/layout/PageTitle';
import { ChatContext } from '../context/ChatContext';

export default function ChatPage() {
  const { activeSessionName } = useContext(ChatContext);

  return (
    <>
      <PageTitle title={activeSessionName} />
      <ChatLayout />
    </>
  );
}
