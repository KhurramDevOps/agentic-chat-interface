import { useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChatContext } from '../context/ChatContext';
import { deleteSessionApi, getHistoryApi, getSessionsApi, sendMessageApi } from '../api/chatApi';
import { useAuth } from './useAuth';

export const chatKeys = {
  sessions: (userId) => [userId, 'sessions'],
  history: (userId, sessionId) => [userId, 'history', sessionId],
};

export function useSessions() {
  const { user } = useAuth();
  return useQuery({
    queryKey: chatKeys.sessions(user?.id),
    queryFn: getSessionsApi,
    enabled: !!user?.id,
    staleTime: 30000,
    select: (data) => data.sessions || [],
  });
}

export function useHistory(sessionId) {
  const { user } = useAuth();
  return useQuery({
    queryKey: chatKeys.history(user?.id, sessionId),
    queryFn: () => getHistoryApi(sessionId),
    enabled: !!user?.id && !!sessionId,
    staleTime: 0,
    select: (data) => data.messages || [],
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { setActiveSessionId, setActiveSessionName } = useContext(ChatContext);

  return useMutation({
    mutationFn: sendMessageApi,
    onSuccess: (data, variables) => {
      const sessionId = data.session_id || data.sessionId;
      if (!variables.session_id && sessionId) {
        setActiveSessionId(sessionId);
      }
      if (data.session_name || data.name) {
        setActiveSessionName(data.session_name || data.name);
      }
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(user?.id) });
      if (sessionId) {
        queryClient.invalidateQueries({ queryKey: chatKeys.history(user?.id, sessionId) });
      }
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { activeSessionId, startNewChat } = useContext(ChatContext);

  return useMutation({
    mutationFn: deleteSessionApi,
    onSuccess: (_, deletedSessionId) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(user?.id) });
      queryClient.removeQueries({ queryKey: chatKeys.history(user?.id, deletedSessionId) });
      if (activeSessionId === deletedSessionId) {
        startNewChat();
      }
    },
  });
}
