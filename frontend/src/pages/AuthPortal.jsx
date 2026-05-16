import React, { useState } from 'react';
import { Container, Row, Col } from 'react-bootstrap';

import AuthCard   from '../components/AuthCard';
import AuthHeader from '../components/AuthHeader';
import AuthForm   from '../components/AuthForm';
import AuthToggle from '../components/AuthToggle';
import '../styles/AuthPortal.css';

export default function AuthPortal() {
  const [isLogin,  setIsLogin]  = useState(true);
  const [name,     setName]     = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = isLogin
      ? { email, password }
      : { name, email, password };
    console.log(isLogin ? 'Login payload:' : 'Register payload:', payload);
    // TODO: wire up Axios to the Node gateway
  };

  const handleToggle = () => {
    setIsLogin((prev) => !prev);
    setName('');
    setEmail('');
    setPassword('');
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
              <AuthForm
                isLogin={isLogin}
                name={name}
                email={email}
                password={password}
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
