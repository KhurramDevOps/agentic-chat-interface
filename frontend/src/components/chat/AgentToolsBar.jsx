import React from 'react';

const TOOLS = [
  { key: 'search', label: 'Web Search', icon: 'bi-search', title: 'Ask Nexus to search the web' },
  { key: 'image', label: 'Image Gen', icon: 'bi-image', title: 'Ask Nexus to generate an image' },
  { key: 'analysis', label: 'Analysis', icon: 'bi-bar-chart', title: 'Ask Nexus for deeper analysis' },
];

export default function AgentToolsBar({ tools, onToggle }) {
  return (
    <div className="d-flex flex-wrap gap-2 mb-2">
      {TOOLS.map((tool) => (
        <button
          className={`btn btn-nexus-ghost tool-pill ${tools[tool.key] ? 'active' : ''}`}
          key={tool.key}
          onClick={() => onToggle(tool.key)}
          title={tool.title}
          type="button"
        >
          <i className={`bi ${tool.icon} me-2`} />
          {tool.label}
        </button>
      ))}
    </div>
  );
}
