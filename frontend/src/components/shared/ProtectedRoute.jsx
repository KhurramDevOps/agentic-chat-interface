import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import useAuthStore from '../../store/authStore';

/**
 * ProtectedRoute
 * ───────────────
 * Renders child routes only when the user has a valid in-memory token.
 * Redirects to /login otherwise.
 */
function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  return token ? <Outlet /> : <Navigate to="/login" replace />;
}

export default ProtectedRoute;
