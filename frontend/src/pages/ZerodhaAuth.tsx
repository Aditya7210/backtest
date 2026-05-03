import { useCallback, useEffect, useMemo, useState } from 'react';
import { generateZerodhaAccessToken, getAuthStatus, getZerodhaLoginUrl } from '../services/api';

interface AuthState {
  api_key_set: boolean;
  api_secret_set: boolean;
  access_token_set: boolean;
  token_date: string;
  token_is_current_day: boolean;
  auth_ready: boolean;
}

function extractRequestToken(input: string): string {
  const raw = (input || '').trim();
  if (!raw) return '';

  if (raw.includes('request_token=')) {
    try {
      const url = new URL(raw);
      return (url.searchParams.get('request_token') || '').trim();
    } catch {
      const query = raw.includes('?') ? raw.split('?', 2)[1] : raw;
      const params = new URLSearchParams(query);
      const parsed = params.get('request_token');
      if (parsed) return parsed.trim();
    }
  }

  if (raw.startsWith('request_token=')) {
    const token = raw.split('=', 2)[1] || '';
    return token.split('&', 2)[0].trim();
  }

  return raw;
}

function currentStep(loginUrl: string, tokenInput: string, generating: boolean, connected: boolean): 1 | 2 | 3 {
  if (connected || generating || tokenInput.trim()) return 3;
  if (loginUrl) return 2;
  return 1;
}

export default function ZerodhaAuthPage() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestTokenInput, setRequestTokenInput] = useState('');
  const [loginUrl, setLoginUrl] = useState<string>('');
  const [openingLogin, setOpeningLogin] = useState(false);
  const [generatingToken, setGeneratingToken] = useState(false);
  const hudBg = '/photos/zerodha-hud-bg.png';
  const brandLogo = '/photos/unlisted-edge-logo.png';

  const fetchAuth = useCallback(async () => {
    const authState = await getAuthStatus();
    setAuth(authState);
  }, []);

  useEffect(() => {
    let mounted = true;
    const initialLoad = async () => {
      try {
        await fetchAuth();
        if (!mounted) return;
        setError(null);
      } catch (e: unknown) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : 'Failed to load authentication state');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    initialLoad();
    const timer = window.setInterval(async () => {
      try {
        if (mounted) await fetchAuth();
      } catch {
        // silent background refresh
      }
    }, 5000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [fetchAuth]);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const autoDetected = (query.get('request_token') || '').trim();
    if (!autoDetected) return;
    setRequestTokenInput(autoDetected);
    setStatusMessage('Request token detected from redirect URL.');
    const nextUrl = `${window.location.pathname}${window.location.hash || ''}`;
    window.history.replaceState({}, document.title, nextUrl);
  }, []);

  const authReady = useMemo(() => Boolean(auth?.auth_ready), [auth]);
  const tokenValidToday = useMemo(() => Boolean(auth?.token_is_current_day), [auth]);
  const activeStep = useMemo(
    () => currentStep(loginUrl, requestTokenInput, generatingToken, authReady),
    [loginUrl, requestTokenInput, generatingToken, authReady],
  );

  const statusKind = generatingToken ? 'loading' : authReady ? 'success' : 'idle';
  const statusTitle = generatingToken ? 'Generating session...' : authReady ? 'Connected ✓' : 'Not Connected';
  const statusSubtext = tokenValidToday
    ? 'Token valid for today'
    : 'Establish a secure Zerodha session before live execution.';

  const handleOpenLogin = async () => {
    setOpeningLogin(true);
    setStatusMessage(null);
    setError(null);
    try {
      const response = await getZerodhaLoginUrl();
      const url = response.login_url;
      setLoginUrl(url);
      window.open(url, '_blank', 'noopener,noreferrer');
      setStatusMessage('Zerodha login opened. Complete authentication and paste request token.');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unable to generate Zerodha login URL');
    } finally {
      setOpeningLogin(false);
    }
  };

  const handleGenerateToken = async () => {
    setGeneratingToken(true);
    setStatusMessage(null);
    setError(null);
    try {
      const requestToken = extractRequestToken(requestTokenInput);
      if (!requestToken) {
        setError('Please provide a valid request_token.');
        return;
      }
      const response = await generateZerodhaAccessToken(requestToken);
      await fetchAuth();
      setStatusMessage(`Connected. Token generated for ${response.token_date}.`);
      setRequestTokenInput('');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unable to generate access token. Please login again.');
    } finally {
      setGeneratingToken(false);
    }
  };

  return (
    <div className="za-auth-shell">
      <style>{`
        .za-auth-shell {
          width: 100%;
          height: calc(100vh - 56px);
          min-height: calc(100vh - 56px);
          max-height: calc(100vh - 56px);
          display: grid;
          grid-template-columns: 42% 58%;
          background: #ffffff;
          color: #0f172a;
          font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          overflow: hidden;
        }
        .za-left {
          padding: 28px 36px 28px 40px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .za-topbar {
          display: flex;
          align-items: center;
          gap: 10px;
          padding-bottom: 12px;
          border-bottom: 1px solid #eef2f7;
          margin-bottom: 26px;
        }
        .za-logo {
          width: 28px;
          height: 28px;
          border-radius: 999px;
          border: 1px solid #dbe2f0;
          overflow: hidden;
          background: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .za-logo img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .za-system {
          font-size: 13px;
          color: #334155;
          font-weight: 600;
          letter-spacing: 0.01em;
        }
        .za-title {
          margin: 0;
          font-size: 34px;
          line-height: 1.15;
          font-weight: 600;
          color: #0b1020;
        }
        .za-subtitle {
          margin: 10px 0 0;
          font-size: 14px;
          color: #64748b;
          line-height: 1.55;
          max-width: 520px;
        }
        .za-steps {
          margin-top: 28px;
          display: grid;
          gap: 22px;
          position: relative;
          max-width: 620px;
        }
        .za-step {
          display: grid;
          grid-template-columns: 58px 1fr;
          column-gap: 16px;
          position: relative;
        }
        .za-step-marker {
          position: relative;
          display: flex;
          justify-content: center;
          padding-top: 2px;
        }
        .za-step-num {
          width: 34px;
          height: 34px;
          border-radius: 999px;
          border: 1px solid #d7deec;
          color: #6b7280;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.06em;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: #ffffff;
          transition: border-color 200ms ease, color 200ms ease, background 200ms ease;
        }
        .za-step.active .za-step-num {
          color: #4f46e5;
          border-color: #c7d2fe;
          background: #eef2ff;
        }
        .za-step-marker::after {
          content: "";
          position: absolute;
          top: 38px;
          left: 50%;
          transform: translateX(-50%);
          width: 1px;
          height: calc(100% + 18px);
          background: #e5e7eb;
        }
        .za-step:last-child .za-step-marker::after {
          display: none;
        }
        .za-step-title {
          margin: 2px 0 4px;
          font-size: 16px;
          color: #0f172a;
          font-weight: 600;
        }
        .za-step-help {
          margin: 0;
          font-size: 13px;
          color: #64748b;
        }
        .za-button {
          margin-top: 10px;
          width: 100%;
          height: 48px;
          border: 0;
          border-radius: 10px;
          background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%);
          color: #ffffff;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: transform 200ms ease, filter 200ms ease, opacity 200ms ease;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .za-button:hover:not(:disabled) {
          transform: translateY(-1px);
          filter: brightness(1.04);
        }
        .za-button:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }
        .za-inline-link {
          margin-top: 8px;
          display: inline-block;
          font-size: 12px;
          color: #4f46e5;
          text-decoration: none;
        }
        .za-inline-link:hover {
          text-decoration: underline;
        }
        .za-input-wrap {
          margin-top: 10px;
          position: relative;
        }
        .za-input {
          width: 100%;
          height: 48px;
          border-radius: 8px;
          border: 1px solid #e5e7eb;
          padding: 0 42px 0 14px;
          font-size: 14px;
          color: #0f172a;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
          outline: none;
          transition: border-color 200ms ease, box-shadow 200ms ease;
          background: #ffffff;
        }
        .za-input:focus {
          border-color: #4f46e5;
          box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.14);
        }
        .za-input-icon {
          position: absolute;
          right: 12px;
          top: 50%;
          transform: translateY(-50%);
          color: #94a3b8;
          font-size: 12px;
          font-weight: 700;
          pointer-events: none;
        }
        .za-status {
          margin-top: 10px;
          padding-top: 16px;
          border-top: 1px solid #eef2f7;
          display: grid;
          gap: 8px;
          max-width: 620px;
        }
        .za-status-label {
          font-size: 12px;
          color: #94a3b8;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          font-weight: 600;
        }
        .za-status-main {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
        }
        .za-status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #9ca3af;
        }
        .za-status-main.idle { color: #6b7280; }
        .za-status-main.loading { color: #2563eb; }
        .za-status-main.success { color: #16a34a; }
        .za-status-main.loading .za-status-dot {
          background: #2563eb;
          animation: zaPulse 1.1s ease-in-out infinite;
        }
        .za-status-main.success .za-status-dot {
          background: #16a34a;
        }
        .za-status-sub {
          font-size: 13px;
          color: #64748b;
        }
        .za-info { font-size: 12px; color: #475569; }
        .za-error { font-size: 12px; color: #dc2626; }
        .za-spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(255,255,255,0.42);
          border-top-color: #ffffff;
          border-radius: 999px;
          animation: zaSpin 0.7s linear infinite;
        }
        .za-right {
          position: relative;
          overflow: hidden;
          background-position: center;
          background-size: cover;
          background-repeat: no-repeat;
        }
        .za-right-fade {
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, rgba(255,255,255,0.72), rgba(255,255,255,0.26));
        }
        .za-core {
          position: absolute;
          width: 190px;
          height: 190px;
          border-radius: 50%;
          left: 48%;
          top: 57%;
          transform: translate(-50%, -50%);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: #2563eb;
          font-weight: 700;
          font-size: 14px;
          letter-spacing: 0.06em;
          background: rgba(255,255,255,0.95);
          border: 1px solid rgba(100, 116, 139, 0.14);
          box-shadow: 0 18px 34px rgba(15, 23, 42, 0.12);
        }
        .za-core-logo {
          width: 350px;
          height: 350px;
          border-radius: 50%;
          object-fit: cover;
          border: 1px solid #dbe2f0;
          background: #ffffff;
        }
        .za-lock {
          position: absolute;
          width: 66px;
          height: 66px;
          border-radius: 16px;
          background: linear-gradient(135deg, #a78bfa, #7c3aed);
          color: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
          left: 17%;
          top: 60%;
          opacity: 0.92;
          box-shadow: 0 12px 24px rgba(124, 58, 237, 0.25);
        }
        .za-lock svg {
          width: 28px;
          height: 28px;
        }
        .za-right-foot {
          position: absolute;
          left: 50%;
          bottom: 40px;
          transform: translateX(-50%);
          display: inline-flex;
          align-items: center;
          gap: 18px;
          color: #8ea0bd;
          font-size: 13px;
          font-weight: 500;
        }
        .za-right-foot-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .za-right-foot-item span {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #9fb2d6;
          display: inline-block;
        }

        @keyframes zaPulse {
          0% { transform: scale(0.86); opacity: 0.72; }
          50% { transform: scale(1); opacity: 1; }
          100% { transform: scale(0.86); opacity: 0.72; }
        }
        @keyframes zaSpin {
          to { transform: rotate(360deg); }
        }
        @media (max-width: 1100px) {
          .za-auth-shell {
            grid-template-columns: 1fr;
            height: calc(100vh - 56px);
            min-height: calc(100vh - 56px);
            max-height: calc(100vh - 56px);
          }
          .za-left { padding: 20px; }
          .za-right { min-height: 0; }
          .za-core { left: 50%; transform: translate(-50%, -50%); }
          .za-lock { left: 16%; top: 66%; }
          .za-right-foot { bottom: 18px; gap: 12px; font-size: 12px; }
        }
      `}</style>

      <section className="za-left">
        <div className="za-topbar">
          <div className="za-logo">
            <img src={brandLogo} alt="Unlisted Edge" />
          </div>
          <div className="za-system">Algo Trading System</div>
        </div>

        <h1 className="za-title">Zerodha Connection</h1>
        <p className="za-subtitle">Establish a secure session to enable live market execution.</p>

        <div className="za-steps">
          <div className={`za-step ${activeStep === 1 ? 'active' : ''}`}>
            <div className="za-step-marker"><span className="za-step-num">01</span></div>
            <div>
              <h3 className="za-step-title">Authenticate with Zerodha</h3>
              <p className="za-step-help">Redirects to Zerodha for secure authentication</p>
              <button className="za-button" onClick={handleOpenLogin} disabled={openingLogin}>
                {openingLogin ? (
                  <>
                    <span className="za-spinner" />
                    <span>Opening Zerodha Login...</span>
                  </>
                ) : (
                  'Open Zerodha Login'
                )}
              </button>
              {loginUrl ? (
                <a className="za-inline-link" href={loginUrl} target="_blank" rel="noreferrer noopener">
                  Open login URL manually
                </a>
              ) : null}
            </div>
          </div>

          <div className={`za-step ${activeStep === 2 ? 'active' : ''}`}>
            <div className="za-step-marker"><span className="za-step-num">02</span></div>
            <div>
              <h3 className="za-step-title">Enter Request Token</h3>
              <p className="za-step-help">Paste request_token from redirect URL</p>
              <div className="za-input-wrap">
                <input
                  className="za-input"
                  value={requestTokenInput}
                  onChange={(e) => setRequestTokenInput(e.target.value)}
                  placeholder="Paste request_token from redirect URL"
                />
                <span className="za-input-icon">{'</>'}</span>
              </div>
            </div>
          </div>

          <div className={`za-step ${activeStep === 3 ? 'active' : ''}`}>
            <div className="za-step-marker"><span className="za-step-num">03</span></div>
            <div>
              <h3 className="za-step-title">Generate Session</h3>
              <p className="za-step-help">Generate the daily access token for live execution</p>
              <button className="za-button" onClick={handleGenerateToken} disabled={generatingToken || loading}>
                {generatingToken ? (
                  <>
                    <span className="za-spinner" />
                    <span>Generating Access Token...</span>
                  </>
                ) : (
                  'Generate Access Token'
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="za-status">
          <div className="za-status-label">Connection Status</div>
          <div className={`za-status-main ${statusKind}`}>
            <span className="za-status-dot" />
            <span>{statusTitle}</span>
          </div>
          <div className="za-status-sub">{statusSubtext}</div>
          {statusMessage ? <div className="za-info">{statusMessage}</div> : null}
          {error ? <div className="za-error">{error}</div> : null}
        </div>
      </section>

      <section className="za-right" aria-hidden="true" style={{ backgroundImage: `url(${hudBg})` }}>
        <div className="za-right-fade" />
        <div className="za-core">
          <img className="za-core-logo" src={brandLogo} alt="Unlisted Edge" />
        </div>
        <div className="za-lock">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M7.5 10V8.5a4.5 4.5 0 1 1 9 0V10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <rect x="5" y="10" width="14" height="10" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
          </svg>
        </div>
        <div className="za-right-foot">
          <div className="za-right-foot-item"><span />Secure</div>
          <div className="za-right-foot-item"><span />Encrypted</div>
          <div className="za-right-foot-item"><span />Real-time</div>
        </div>
      </section>
    </div>
  );
}
