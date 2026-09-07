import React, { useState, useEffect } from 'react';

export default function StatusBanner() {
  const [status, setStatus] = useState('operational'); // 'operational' | 'degraded' | 'down'
  const [latency, setLatency] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const checkServerHealth = async () => {
      const start = performance.now();
      try {
        await fetch('http://localhost:8000/docs', { method: 'HEAD', mode: 'no-cors' });
        const elapsed = Math.round(performance.now() - start);
        if (isMounted) {
          setLatency(elapsed);
          if (elapsed > 1200) {
            setStatus('degraded');
          } else {
            setStatus('operational');
          }
        }
      } catch (err) {
        if (isMounted) {
          setStatus('down');
          setLatency(null);
        }
      }
    };

    checkServerHealth();
    const interval = setInterval(checkServerHealth, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  if (status === 'operational') {
    return null; // Normal operation: keep screen clean per Section 7.7
  }

  if (status === 'degraded') {
    return (
      <div className="gov-status-banner gov-status-banner-degraded">
        <span>System Status: The backend is responding slowly ({latency}ms). Pages may take longer to load.</span>
      </div>
    );
  }

  return (
    <div className="gov-status-banner gov-status-banner-down">
      <span>System Status: Backend unreachable. Nothing on this screen will load or save until the connection is restored.</span>
      <span style={{ textDecoration: 'underline', cursor: 'pointer' }} onClick={() => window.location.reload()}>
        Retry Connection
      </span>
    </div>
  );
}
