import React, { useState } from 'react';
import AuthLayout from '../components/auth/AuthLayout';
import LoginForm from '../components/auth/LoginForm';
import RegisterForm from '../components/auth/RegisterForm';
import OnboardingModal from '../components/onboarding/OnboardingModal';
import PageTitle from '../components/layout/PageTitle';
import { useAuth } from '../hooks/useAuth';

export default function AuthPage() {
  const [mode, setMode] = useState('login');
  const [showOnboarding, setShowOnboarding] = useState(false);
  const { user } = useAuth();

  return (
    <>
      <PageTitle title={mode === 'login' ? 'Sign In' : 'Create Account'} />
      <AuthLayout mode={mode} onModeChange={setMode}>
        {mode === 'login' ? (
          <LoginForm />
        ) : (
          <RegisterForm onRegistered={() => setShowOnboarding(true)} />
        )}
      </AuthLayout>
      {showOnboarding && user ? (
        <OnboardingModal user={user} onClose={() => setShowOnboarding(false)} />
      ) : null}
    </>
  );
}
