import React, { useState } from 'react';
import { Container, Row, Col } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';

import AuthCard   from '../components/auth/AuthCard';
import AuthHeader from '../components/auth/AuthHeader';
import AuthForm   from '../components/auth/AuthForm';
import AuthToggle from '../components/auth/AuthToggle';
import useAuthStore from '../store/authStore';
import '../styles/AuthPortal.css';

export default function AuthPortal() {
  const [isLogin,  setIsLogin]  = useState(true);
  const [name,     setName]     = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');

  const login    = useAuthStore((s) => s.login);
  const signup   = useAuthStore((s) => s.signup);
  const isLoading = useAuthStore((s) => s.isLoading);
  const error    = useAuthStore((s) => s.error);
  const clearError = useAuthStore((s) => s.clearError);

  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    clearError();

    const success = isLogin
      ? await login(email, password)
      : await signup(name, email, password);

    if (success) navigate('/chat');
  };

  const handleToggle = () => {
    setIsLogin((prev) => !prev);
    setName('');
    setEmail('');
    setPassword('');
    clearError();
  };

  return (
    <div className="auth-page">
      <Container
        fluid
        className="d-flex align-items-center justify-content-center"
        style={{ minHeight: '100vh' }}
      >
        <Row className="w-100 justify-content-center">
          <Col xs={11} sm={8} md={6} lg={4}>
            <AuthCard>
              <AuthHeader isLogin={isLogin} />
              {error && (
                <div className="alert alert-danger py-2 mb-3" role="alert">
                  {error}
                </div>
              )}
              <AuthForm
                isLogin={isLogin}
                name={name}
                email={email}
                password={password}
                isLoading={isLoading}
                onNameChange={(e)     => setName(e.target.value)}
                onEmailChange={(e)    => setEmail(e.target.value)}
                onPasswordChange={(e) => setPassword(e.target.value)}
                onSubmit={handleSubmit}
              />
              <AuthToggle isLogin={isLogin} onToggle={handleToggle} />
            </AuthCard>
          </Col>
        </Row>
      </Container>
    </div>
  );
}
