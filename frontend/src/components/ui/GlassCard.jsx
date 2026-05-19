import React from 'react';

export default function GlassCard({ as: Element = 'div', className = '', children, ...props }) {
  return (
    <Element className={`glass-card ${className}`.trim()} {...props}>
      {children}
    </Element>
  );
}
