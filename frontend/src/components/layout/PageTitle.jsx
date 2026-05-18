import { useEffect } from 'react';

export default function PageTitle({ title }) {
  useEffect(() => {
    document.title = title ? `${title} - Nexus AI` : 'Nexus AI';
    return () => {
      document.title = 'Nexus AI';
    };
  }, [title]);

  return null;
}
