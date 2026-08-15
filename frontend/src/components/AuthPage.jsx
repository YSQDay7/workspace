import { useEffect, useState } from 'react';
import { KeyRound, LogIn, RefreshCw, UserPlus, Waves } from 'lucide-react';
import { fetchCaptcha, login, register, setRefreshToken } from '../api';

export default function AuthPage({ onAuthed, onGuest, allowGuest = true, notice = '' }) {
  const isAgent = window.location.pathname === '/agent';
  const USERNAME_RE = /^[\u4e00-\u9fa5A-Za-z0-9_]{3,32}$/;
  const PASSWORD_RE = /^(?=.*[A-Za-z])(?=.*\d)\S{8,32}$/;
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function loadCaptcha() {
    try {
      const data = await fetchCaptcha();
      setCaptchaId(data.captcha_id);
      setCaptchaImage(data.image);
      setCaptchaCode('');
    } catch (err) {
      setError('验证码加载失败，请稍后重试');
    }
  }

  useEffect(() => {
    loadCaptcha();
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    if (!username.trim() || !password || (mode === 'register' && !captchaCode.trim())) {
      setError('请填写完整信息');
      return;
    }
    if (!USERNAME_RE.test(username.trim())) {
      setError('用户名需为 3-32 位，仅支持中文、字母、数字和下划线');
      return;
    }
    if (!PASSWORD_RE.test(password)) {
      setError('密码需为 8-32 位，必须包含字母和数字，且不能包含空格');
      return;
    }
    setLoading(true);
    try {
      const payload =
        mode === 'register'
          ? {
              username: username.trim(),
              password,
              captcha_id: captchaId,
              captcha_code: captchaCode,
            }
          : { username: username.trim(), password };
      const data = mode === 'login' ? await login(payload) : await register(payload);
      if (data.refresh_token) setRefreshToken(data.refresh_token);
      onAuthed(data.token, data.user);
    } catch (err) {
      setError(err.message || '操作失败');
      loadCaptcha();
    } finally {
      setLoading(false);
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError('');
    loadCaptcha();
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark"><Waves size={22} /></span>
          <div>
            <h1>{isAgent ? '客服工作台登录' : '杭州智游助手'}</h1>
            <p>{isAgent ? '请使用客服或管理员工号登录' : '登录后保存你的对话与行程'}</p>
          </div>
        </div>

        <div className="auth-tabs">
          <button
            type="button"
            className={mode === 'login' ? 'active' : ''}
            onClick={() => switchMode('login')}
          >
            <LogIn size={15} /> 登录
          </button>
          <button
            type="button"
            className={mode === 'register' ? 'active' : ''}
            onClick={() => switchMode('register')}
          >
            <UserPlus size={15} /> 注册
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>用户名</span>
            <input
              type="text"
              value={username}
              autoComplete="username"
              placeholder="3-32 个字符"
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder="8-32 位，含字母和数字"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {mode === 'register' && (
            <label className="field">
              <span>图形验证码</span>
              <div className="captcha-row">
                <input
                  type="text"
                  value={captchaCode}
                  placeholder="输入图中字符"
                  onChange={(event) => setCaptchaCode(event.target.value)}
                />
                <button type="button" className="captcha-image" onClick={loadCaptcha} title="刷新验证码">
                  {captchaImage ? <img src={captchaImage} alt="验证码" /> : <RefreshCw size={18} />}
                </button>
                <button type="button" className="captcha-refresh" onClick={loadCaptcha} title="刷新验证码">
                  <RefreshCw size={15} />
                </button>
              </div>
            </label>
          )}

          {(notice || error) && (
            <p className="auth-error">
              {notice || error}
              {isAgent && notice && (
                <span className="auth-error-link">
                  <a href="/">前往杭州智游助手登录</a>
                </span>
              )}
            </p>
          )}

          <button type="submit" className="auth-submit" disabled={loading}>
            <KeyRound size={16} />
            {loading ? '处理中...' : mode === 'login' ? (isAgent ? '进入工作台' : '登录') : '注册并登录'}
          </button>
        </form>

        {allowGuest && (
          <button type="button" className="guest-link" onClick={onGuest}>
            先不登录，以游客身份体验
          </button>
        )}
        {isAgent ? (
          <a className="auth-switch-link" href="/">前往杭州智游助手登录</a>
        ) : (
          <a className="auth-switch-link subtle" href="/agent">客服工作台登录</a>
        )}
      </div>
    </div>
  );
}
