import React, { createContext, useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { loginApi, logoutApi, registerApi } from '../api/authApi';
import { clearToken, getStoredUser, getToken, setStoredUser, setToken } from '../utils/tokenUtils';

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState(getStoredUser);
  const [token, setTokenState] = useState(getToken);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const normalizeAuthPayload = useCallback((data) => ({
    token: data.token || data.accessToken,
    user: data.user || {
      id: data.id,
      name: data.name,
      email: data.email,
    },
  }), []);

  const acceptAuth = useCallback((data) => {
    const payload = normalizeAuthPayload(data);
    setToken(payload.token);
    setStoredUser(payload.user);
    setTokenState(payload.token);
    setUser(payload.user);
    return payload;
  }, [normalizeAuthPayload]);

  const login = useCallback(async (credentials) => {
    setIsLoading(true);
    setError(null);
    try {
      return acceptAuth(await loginApi(credentials));
    } catch (err) {
      const message = err.response?.data?.error || err.response?.data?.message || 'Login failed';
      setError(message);
      throw new Error(message);
    } finally {
      setIsLoading(false);
    }
  }, [acceptAuth]);

  const register = useCallback(async (userData) => {
    setIsLoading(true);
    setError(null);
    try {
      return acceptAuth(await registerApi(userData));
    } catch (err) {
      const message = err.response?.data?.error || err.response?.data?.message || 'Registration failed';
      setError(message);
      throw new Error(message);
    } finally {
      setIsLoading(false);
    }
  }, [acceptAuth]);

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } catch {
      // Logout must still clear local state if the network is unavailable.
    }
    queryClient.clear();
    clearToken();
    setTokenState(null);
    setUser(null);
  }, [queryClient]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        error,
        login,
        register,
        logout,
        setError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
