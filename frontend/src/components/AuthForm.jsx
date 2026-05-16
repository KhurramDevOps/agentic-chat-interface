import React from 'react';
import { Form, Button } from 'react-bootstrap';
import '../styles/AuthPortal.css';

export default function AuthForm({
  isLogin,
  name,
  email,
  password,
  onNameChange,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}) {
  return (
    <Form onSubmit={onSubmit}>

      {/* Name — register only */}
      {!isLogin && (
        <Form.Group className="mb-3" controlId="formName">
          <Form.Label className="auth-label">Name</Form.Label>
          <Form.Control
            type="text"
            placeholder="Your name"
            value={name}
            onChange={onNameChange}
            className="auth-input"
            required
          />
        </Form.Group>
      )}

      {/* Email */}
      <Form.Group className="mb-3" controlId="formEmail">
        <Form.Label className="auth-label">Email</Form.Label>
        <Form.Control
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={onEmailChange}
          className="auth-input"
          required
        />
      </Form.Group>

      {/* Password */}
      <Form.Group className="mb-4" controlId="formPassword">
        <Form.Label className="auth-label">Password</Form.Label>
        <Form.Control
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={onPasswordChange}
          className="auth-input"
          required
        />
      </Form.Group>

      {/* Submit */}
      <Button type="submit" className="auth-submit-btn">
        {isLogin ? 'Sign In' : 'Register'}
      </Button>

    </Form>
  );
}
