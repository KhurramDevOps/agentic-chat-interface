import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import config from '../config';

const topics = ['Tech', 'Science', 'Business', 'Arts', 'Health', 'Sports', 'Finance', 'Gaming', 'Music', 'Other'];
const responseStyles = [
  { id: 'concise', label: 'Concise and to the point' },
  { id: 'detailed', label: 'Detailed and thorough' },
  { id: 'casual', label: 'Casual and friendly' },
  { id: 'formal', label: 'Formal and professional' },
];

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('nexus_user')) || {};
  } catch {
    return {};
  }
}

export default function Onboarding() {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = 'Nexus AI';
  }, []);
  const storedUser = useMemo(getStoredUser, []);
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: storedUser.name || '',
    nickname: '',
    occupation: '',
    location: '',
    interests: [],
    responseStyle: 'casual',
    memoryEnabled: true,
    webSearchEnabled: true,
  });

  const update = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    setError('');
  };

  const toggleInterest = (topic) => {
    setForm((current) => ({
      ...current,
      interests: current.interests.includes(topic)
        ? current.interests.filter((item) => item !== topic)
        : [...current.interests, topic],
    }));
  };

  const continueStep = async () => {
    if (step === 1 && !form.name.trim()) {
      setError('Tell Nexus what to call you.');
      return;
    }
    if (step < 3) {
      setStep((current) => current + 1);
      return;
    }

    setSaving(true);
    setError('');
    try {
      const response = await fetch(`${config.apiUrl}/api/users/onboarding`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('nexus_token')}`,
        },
        body: JSON.stringify(form),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Could not save onboarding.');
      localStorage.setItem('nexus_user', JSON.stringify(data.user || storedUser));
      navigate('/chat');
    } catch (err) {
      setError(err.message || 'Could not save onboarding.');
    } finally {
      setSaving(false);
    }
  };

  const skip = () => {
    if (step < 3) setStep((current) => current + 1);
  };

  return (
    <main className="onboarding-page">
      <section className="onboarding-card glass-card">
        <div className="onboarding-progress">
          <span>Step {step} of 3</span>
          <div>
            <i style={{ width: `${(step / 3) * 100}%` }} />
          </div>
        </div>

        {step === 1 ? (
          <div className="onboarding-step">
            <h1>What should Nexus call you?</h1>
            <label htmlFor="onboarding-name">Your name</label>
            <input
              id="onboarding-name"
              className="form-control"
              onChange={(event) => update('name', event.target.value)}
              placeholder="Your name"
              value={form.name}
            />
            <label htmlFor="onboarding-nickname">Your nickname (optional)</label>
            <input
              id="onboarding-nickname"
              className="form-control"
              onChange={(event) => update('nickname', event.target.value)}
              placeholder="Nickname"
              value={form.nickname}
            />
            <p>Nexus will use this to personalise every conversation</p>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="onboarding-step">
            <h1>Tell Nexus about yourself</h1>
            <label htmlFor="onboarding-occupation">What do you do?</label>
            <input
              id="onboarding-occupation"
              className="form-control"
              onChange={(event) => update('occupation', event.target.value)}
              placeholder="Student, developer, designer..."
              value={form.occupation}
            />
            <label htmlFor="onboarding-location">Where are you based?</label>
            <input
              id="onboarding-location"
              className="form-control"
              onChange={(event) => update('location', event.target.value)}
              placeholder="City, country"
              value={form.location}
            />
            <span className="onboarding-label">Topics I care about</span>
            <div className="chip-grid">
              {topics.map((topic) => (
                <button
                  className={`tool-chip ${form.interests.includes(topic) ? 'active' : ''}`}
                  key={topic}
                  onClick={() => toggleInterest(topic)}
                  type="button"
                >
                  {topic}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="onboarding-step">
            <h1>How should Nexus respond?</h1>
            <span className="onboarding-label">Response style</span>
            <div className="style-options">
              {responseStyles.map((style) => (
                <label className="style-option" key={style.id}>
                  <input
                    checked={form.responseStyle === style.id}
                    name="responseStyle"
                    onChange={() => update('responseStyle', style.id)}
                    type="radio"
                  />
                  {style.label}
                </label>
              ))}
            </div>
            <label className="toggle-row">
              <input
                checked={form.memoryEnabled}
                onChange={(event) => update('memoryEnabled', event.target.checked)}
                type="checkbox"
              />
              Enable long-term memory
            </label>
            <label className="toggle-row">
              <input
                checked={form.webSearchEnabled}
                onChange={(event) => update('webSearchEnabled', event.target.checked)}
                type="checkbox"
              />
              Enable web search by default
            </label>
          </div>
        ) : null}

        {error ? <div className="chat-error mt-3">{error}</div> : null}

        <div className="onboarding-actions">
          <button className="btn btn-nexus-ghost" disabled={step === 1 || saving} onClick={() => setStep((current) => current - 1)} type="button">
            Back
          </button>
          {step > 1 ? <button className="skip-link" disabled={saving} onClick={skip} type="button">Skip</button> : <span />}
          <button className="btn btn-nexus-primary" disabled={saving} onClick={continueStep} type="button">
            {saving ? 'Saving...' : step === 3 ? 'Finish' : 'Continue'}
          </button>
        </div>
      </section>
    </main>
  );
}
