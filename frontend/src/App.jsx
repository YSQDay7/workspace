import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  CloudSun,
  Compass,
  Database,
  Headset,
  LogOut,
  Map as MapIcon,
  MapPin,
  MessageSquarePlus,
  Route,
  Send,
  Sparkles,
  Ticket,
  Trash2,
  User,
  Waves,
} from 'lucide-react';
import {
  GUEST_KEY,
  SESSION_KEY,
  USER_KEY,
  clearRefreshToken,
  clearToken,
  createSession,
  createHandover,
  deleteMessage,
  deleteSession,
  fetchHotQuestions,
  fetchSessionMessages,
  fetchSessions,
  getJson,
  getToken,
  logout as apiLogout,
  rateTicket,
  refreshAccess,
  setToken,
  streamChat,
  webStorage,
} from './api';
import AgentConsole from './components/AgentConsole';
import AuthPage from './components/AuthPage';
import ItineraryTimeline from './components/ItineraryTimeline';
import MapView from './components/MapView';
import SourceList from './components/SourceList';
import WeatherCard from './components/WeatherCard';

const DEFAULT_SUGGESTIONS = [
  '西湖有哪些经典景点？',
  '杭州一日游路线怎么安排？',
  '灵隐寺门票多少钱？',
  '杭州最近天气怎么样？',
];

function IntentBadges({ intents }) {
  const badges = [];
  if (intents.includes('weather')) badges.push({ icon: CloudSun, label: '实时天气' });
  if (intents.includes('ticket')) badges.push({ icon: Ticket, label: '票务数据' });
  if (intents.includes('route')) badges.push({ icon: Route, label: '路线时间表' });
  if (badges.length === 0 && (intents.includes('knowledge') || intents.includes('greeting'))) {
    badges.push({ icon: Database, label: '知识库' });
  }
  if (badges.length === 0) return null;
  return (
    <div className="intent-badges">
      {badges.map((badge) => (
        <span className="intent-badge" key={badge.label}>
          <badge.icon size={12} />
          {badge.label}
        </span>
      ))}
    </div>
  );
}

function EmptyPanel({ icon: Icon, text }) {
  return (
    <div className="panel-empty">
      <Icon size={28} />
      <p>{text}</p>
    </div>
  );
}

function normalizeMessages(rows) {
  return (rows || []).map((message) => ({
    ...message,
    sources: message.sources || [],
    intents: message.meta?.intents || [],
    itinerary: message.meta?.itinerary || null,
    weather: message.meta?.weather || null,
    ticket_hits: message.meta?.ticket_hits || [],
    suggested: message.meta?.suggested_questions || [],
  }));
}

function lastResponseFromMessages(rows) {
  const normalized = normalizeMessages(rows);
  const assistants = normalized.filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  if (!last) return null;
  return {
    sources: last.sources || [],
    itinerary: last.itinerary || null,
    ticket_hits: last.ticket_hits || [],
    intents: last.intents || [],
    suggested_questions: last.suggested || [],
  };
}

export default function App() {
  const isAgentPath = window.location.pathname === '/agent';
  const [token, setTokenState] = useState(() => getToken());
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(webStorage().getItem(USER_KEY) || 'null');
    } catch (error) {
      return null;
    }
  });
  const [guestMode, setGuestMode] = useState(() => webStorage().getItem(GUEST_KEY) === '1');
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(() => {
    const saved = webStorage().getItem(SESSION_KEY);
    return saved ? Number(saved) : null;
  });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [weather, setWeather] = useState(null);
  const [attractions, setAttractions] = useState([]);
  const [pois, setPois] = useState([]);
  const [scenicAreas, setScenicAreas] = useState([]);
  const [hotQuestions, setHotQuestions] = useState([]);
  const [hotSource, setHotSource] = useState('empty');
  const [backendOk, setBackendOk] = useState(false);
  const [activeTab, setActiveTab] = useState('地图');
  const [lastResponse, setLastResponse] = useState(null);
  const [selectedScenic, setSelectedScenic] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [handover, setHandover] = useState(null);
  const [showRating, setShowRating] = useState(false);
  const [rating, setRating] = useState(0);
  const [ratingComment, setRatingComment] = useState('');
  const scrollRef = useRef(null);

  async function fetchHotQuestionsData() {
    try {
      const data = await fetchHotQuestions();
      setHotQuestions(data.questions || []);
      setHotSource(data.source || 'empty');
    } catch (error) {
      // keep existing hot questions
    }
  }

  async function loadSessions() {
    try {
      const data = await fetchSessions();
      setSessions(data.sessions || []);
    } catch (error) {
      // ignore
    }
  }

  async function openSession(sessionId) {
    setCurrentSessionId(sessionId);
    webStorage().setItem(SESSION_KEY, String(sessionId));
    try {
      const data = await fetchSessionMessages(sessionId);
      setMessages(normalizeMessages(data.messages));
      setLastResponse(lastResponseFromMessages(data.messages));
    } catch (error) {
      setMessages([]);
    }
  }

  async function createNewSession() {
    const data = await createSession('新对话');
    setCurrentSessionId(data.session_id);
    webStorage().setItem(SESSION_KEY, String(data.session_id));
    setMessages([]);
    setLastResponse(null);
    if (token) loadSessions();
  }

  async function restoreSession() {
    if (!getToken()) return;
    const saved = webStorage().getItem(SESSION_KEY);
    if (saved) {
      try {
        const data = await fetchSessionMessages(Number(saved));
        setCurrentSessionId(Number(saved));
        setMessages(normalizeMessages(data.messages));
        setLastResponse(lastResponseFromMessages(data.messages));
        loadSessions();
        return;
      } catch (error) {
        // fall through to latest session
      }
    }
    try {
      const data = await fetchSessions();
      setSessions(data.sessions || []);
      if (data.sessions?.length) {
        await openSession(data.sessions[0].id);
      } else {
        await createNewSession();
      }
    } catch (error) {
      // ignore
    }
  }

  function handleAuthed(newToken, newUser) {
    setToken(newToken);
    webStorage().setItem(USER_KEY, JSON.stringify(newUser));
    webStorage().removeItem(GUEST_KEY);
    setTokenState(newToken);
    setUser(newUser);
    setGuestMode(false);
    restoreSession();
  }

  async function handleGuest() {
    webStorage().setItem(GUEST_KEY, '1');
    setGuestMode(true);
    const data = await createSession('游客会话');
    setCurrentSessionId(data.session_id);
    webStorage().setItem(SESSION_KEY, String(data.session_id));
    setMessages([]);
  }

  async function handleLogout() {
    try {
      await apiLogout();
    } catch (error) {
      // ignore
    }
    clearToken();
    clearRefreshToken();
    webStorage().removeItem(USER_KEY);
    webStorage().removeItem(GUEST_KEY);
    webStorage().removeItem(SESSION_KEY);
    setTokenState(null);
    setUser(null);
    setGuestMode(false);
    setSessions([]);
    setCurrentSessionId(null);
    setMessages([]);
    setLastResponse(null);
  }

  useEffect(() => {
    getJson('/api/attractions')
      .then((data) => setAttractions(data.attractions || []))
      .catch(() => {});
    getJson('/api/pois')
      .then((data) => setPois(data.pois || []))
      .catch(() => {});
    getJson('/api/scenic-areas')
      .then((data) => setScenicAreas(data.scenic_areas || []))
      .catch(() => {});
    getJson('/api/tools/weather')
      .then((data) => setWeather(data))
      .catch(() => {});
    getJson('/api/health')
      .then((data) => setBackendOk(data.status === 'ok'))
      .catch(() => setBackendOk(false));
    fetchHotQuestionsData();
    if (!isAgentPath && getToken()) {
      restoreSession();
    } else if (guestMode && currentSessionId) {
      openSession(currentSessionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!token && !user) return undefined;
    const timer = setInterval(() => {
      refreshAccess().then((ok) => {
        if (!ok) {
          clearToken();
          clearRefreshToken();
          setTokenState(null);
          setUser(null);
          setGuestMode(false);
        }
      });
    }, 120000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, loading]);

  function updateLastAssistant(updater) {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      if (last.role !== 'assistant') return prev;
      return [...prev.slice(0, -1), updater(last)];
    });
  }

  async function sendMessage(text) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    setInput('');

    let sessionId = currentSessionId;
    if (!sessionId) {
      const data = await createSession('新对话');
      sessionId = data.session_id;
      setCurrentSessionId(sessionId);
      webStorage().setItem(SESSION_KEY, String(sessionId));
      if (token) loadSessions();
    }

    const tempUser = { id: `temp-user-${Date.now()}`, role: 'user', content: question };
    const tempAssistant = {
      id: `temp-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      streaming: true,
      sources: [],
      suggested: [],
      intents: [],
      itinerary: null,
      weather: null,
      ticket_hits: [],
    };
    setMessages((prev) => [...prev, tempUser, tempAssistant]);
    setLoading(true);

    try {
      let doneReceived = false;
      await streamChat(sessionId, question, selectedScenic ? [selectedScenic] : null, (eventName, data) => {
        if (eventName === 'session') {
          if (data.handover) setHandover(data.handover);
        } else if (eventName === 'meta') {
          updateLastAssistant((last) => ({
            ...last,
            sources: data.sources || [],
            intents: data.intents || [],
            itinerary: data.itinerary || null,
            weather: data.weather || null,
            ticket_hits: data.ticket_hits || [],
          }));
        } else if (eventName === 'token') {
          updateLastAssistant((last) => ({
            ...last,
            content: last.content + (data.text || ''),
          }));
        } else if (eventName === 'done') {
          doneReceived = true;
          updateLastAssistant((last) => ({
            ...last,
            content: data.reply || last.content,
            streaming: false,
            suggested: data.suggested_questions || [],
            sources: data.sources || [],
            intents: data.intents || [],
            itinerary: data.itinerary || null,
            weather: data.weather || null,
            ticket_hits: data.ticket_hits || [],
          }));
          setLastResponse(data);
          setActiveTab(data.itinerary ? '行程' : data.sources?.length ? '来源' : '地图');
        } else if (eventName === 'error') {
          setLastResponse(null);
          updateLastAssistant((last) => ({
            ...last,
            content: `抱歉，出错了：${data.message || '请稍后再试'}`,
            streaming: false,
          }));
        }
      });
      if (!doneReceived) {
        updateLastAssistant((last) => ({
          ...last,
          content: '抱歉，回答被中断了，请再试一次。',
          streaming: false,
        }));
        setLastResponse(null);
      }
      const fresh = await fetchSessionMessages(sessionId);
      setMessages(normalizeMessages(fresh.messages));
      const rows = fresh.messages || [];
      setLastResponse(rows[rows.length - 1]?.role === 'assistant' ? lastResponseFromMessages(rows) : null);
      fetchHotQuestionsData();
      if (token) loadSessions();
    } catch (error) {
      updateLastAssistant((last) => ({
        ...last,
        content: `抱歉，服务暂时开小差了：${error.message}`,
        streaming: false,
      }));
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteMessage(messageId) {
    if (!currentSessionId) return;
    if (typeof messageId === 'number') {
      try {
        await deleteMessage(messageId, currentSessionId);
      } catch (error) {
        // still remove locally
      }
    }
    setMessages((prev) => prev.filter((message) => message.id !== messageId));
  }

  async function handleManualHandover() {
    if (!currentSessionId || handover) return;
    try {
      const data = await createHandover(currentSessionId, '用户主动转人工');
      setHandover(data.ticket);
    } catch (error) {
      // keep robot service
    }
  }

  async function handleRateSubmit() {
    if (!handover?.id || rating < 1) return;
    try {
      await rateTicket(handover.id, rating, ratingComment);
    } catch (error) {
      // ignore
    }
    setShowRating(false);
    setRating(0);
    setRatingComment('');
  }

  useEffect(() => {
    if (!handover?.id || !currentSessionId) return undefined;
    const timer = setInterval(async () => {
      try {
        const data = await fetchSessionMessages(currentSessionId);
        setMessages(normalizeMessages(data.messages));
        const closed = (data.messages || []).find(
          (item) => item.sender_type === 'system' && item.content.includes('客服已结束'),
        );
        if (closed && handover.status !== 'closed') {
          setHandover({ ...handover, status: 'closed' });
          setShowRating(true);
        }
      } catch (error) {
        // ignore
      }
    }, 4000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handover?.id, handover?.status, currentSessionId]);

  function requestDeleteSession(sessionId) {
    setConfirmDeleteId(sessionId);
  }

  async function doDeleteSession() {
    const sessionId = confirmDeleteId;
    if (sessionId == null) return;
    setConfirmDeleteId(null);
    try {
      await deleteSession(sessionId);
    } catch (error) {
      // still remove locally
    }
    const remaining = sessions.filter((session) => session.id !== sessionId);
    setSessions(remaining);
    if (currentSessionId === sessionId) {
      setMessages([]);
      setCurrentSessionId(null);
      webStorage().removeItem(SESSION_KEY);
      setLastResponse(null);
      if (remaining.length > 0) {
        await openSession(remaining[0].id);
      } else {
        await createNewSession();
      }
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  if (isAgentPath) {
    if (!token || !user || !['customer_service', 'admin'].includes(user.role)) {
      const notice = token && user ? '该账号没有客服权限，请使用客服账号登录，或返回杭州智游助手。' : '';
      return (
        <AuthPage
          onAuthed={handleAuthed}
          onGuest={handleGuest}
          allowGuest={false}
          notice={notice}
        />
      );
    }
    return <AgentConsole user={user} onLogout={handleLogout} />;
  }

  if (!token && !guestMode) {
    return <AuthPage onAuthed={handleAuthed} onGuest={handleGuest} allowGuest />;
  }

  const hotList = hotQuestions.length > 0 ? hotQuestions : DEFAULT_SUGGESTIONS;
  const routeScenicSet = new Set(
    (lastResponse?.itinerary?.stops || []).map((stop) => stop.scenic_area).filter(Boolean),
  );
  const showDetailed = !lastResponse?.itinerary || routeScenicSet.size <= 2;
  const visibleAttractions = selectedScenic
    ? attractions.filter((item) => item.scenic_area === selectedScenic)
    : showDetailed
      ? routeScenicSet.size
        ? attractions.filter((item) => routeScenicSet.has(item.scenic_area))
        : attractions
      : [];
  const visiblePois =
    showDetailed && (selectedScenic || routeScenicSet.size)
      ? pois.filter((item) =>
          selectedScenic ? item.scenic_area === selectedScenic : routeScenicSet.has(item.scenic_area),
        )
      : [];

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark"><Waves size={20} /></span>
          <div>
            <h1>杭州智游助手</h1>
            <p>杭州全市多景区智能问答与行程规划</p>
          </div>
        </div>
        <div className="header-right">
          <span className={`status-dot ${backendOk ? 'ok' : 'down'}`} />
          <span className="header-user">
            <User size={14} />
            {user ? user.username : '游客模式'}
          </span>
          {user && (
            <button type="button" className="header-logout" onClick={handleLogout} title="退出登录">
              <LogOut size={15} />
            </button>
          )}
        </div>
      </header>

      <div className="app-body">
        <aside className="left-sidebar">
          <WeatherCard weather={weather} />

          <section className="hot-section">
            <div className="section-title">
              <Sparkles size={15} />
              <h3>{hotSource === 'real' ? '实时热门回答' : '热门问题'}</h3>
              {hotSource === 'real' && <span className="live-tag">实时</span>}
            </div>
            <ul className="hot-list">
              {hotList.map((item, index) => {
                const question = typeof item === 'string' ? item : item.question;
                const count = typeof item === 'string' ? null : item.count;
                return (
                  <li key={`${question}-${index}`}>
                    <button type="button" onClick={() => sendMessage(question)}>
                      <span>{question}</span>
                      {count !== null && <em>{count} 次</em>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          {user && (
            <section className="session-section">
              <div className="section-title">
                <MessageSquarePlus size={15} />
                <h3>我的会话</h3>
                <button type="button" className="new-session-btn" onClick={createNewSession}>
                  <Send size={12} /> 新建
                </button>
              </div>
              <ul className="session-list">
                {sessions.map((session) => (
                  <li key={session.id}>
                    <button
                      type="button"
                      className={`session-item-btn ${session.id === currentSessionId ? 'active' : ''}`}
                      onClick={() => openSession(session.id)}
                    >
                      <span>{session.title}</span>
                      <small>{session.message_count} 条</small>
                    </button>
                    <button
                      type="button"
                      className="session-delete-btn"
                      title="删除对话"
                      onClick={(event) => {
                        event.stopPropagation();
                        requestDeleteSession(session.id);
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="scenic-section">
            <div className="section-title">
              <MapPin size={15} />
              <h3>景区切换</h3>
            </div>
            <div className="scenic-grid">
              {scenicAreas.map((area) => (
                <button
                  type="button"
                  key={area.code}
                  className={`scenic-chip ${selectedScenic === area.code ? 'active' : ''}`}
                  onClick={() => setSelectedScenic(selectedScenic === area.code ? null : area.code)}
                >
                  {area.name}
                </button>
              ))}
            </div>
            {selectedScenic && (
              <button type="button" className="scenic-clear" onClick={() => setSelectedScenic(null)}>
                清除筛选，查看全部景区
              </button>
            )}
          </section>
        </aside>

        <main className="chat-panel">
          <div className="chat-scroll" ref={scrollRef}>
            {messages.map((message, index) => {
              const isUser = message.role === 'user';
              return (
                <div className="message-group" key={`${message.role}-${message.id || index}`}>
                  <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
                    {!isUser && (
                      <span className="avatar assistant">
                        <Bot size={17} />
                      </span>
                    )}
                    {isUser && !message.streaming && (
                      <button
                        type="button"
                        className="delete-message"
                        title="删除这条消息"
                        onClick={() => handleDeleteMessage(message.id)}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                    <div className={`bubble ${message.streaming ? 'streaming' : ''} ${isUser ? 'user-bubble' : ''}`}>
                      {message.streaming && message.content === '' ? (
                        <span className="typing-dots"><i /><i /><i /></span>
                      ) : (
                        <div className="markdown-body">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                          {message.streaming && <span className="stream-cursor" />}
                        </div>
                      )}
                    </div>
                    {isUser && (
                      <span className="avatar user"><User size={17} /></span>
                    )}
                    {!isUser && !message.streaming && (
                      <button
                        type="button"
                        className="delete-message"
                        title="删除这条消息"
                        onClick={() => handleDeleteMessage(message.id)}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                  {!isUser && !message.streaming && message.intents && message.intents.length > 0 && (
                    <IntentBadges intents={message.intents} />
                  )}
                  {!isUser && !message.streaming && message.suggested && message.suggested.length > 0 && (
                    <div className="suggested-row">
                      {message.suggested.map((question) => (
                        <button
                          type="button"
                          className="chip"
                          key={question}
                          onClick={() => sendMessage(question)}
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {handover && handover.status !== 'closed' && (
            <div className="handover-banner">
              <Headset size={16} />
              <span>已转人工客服，客服接入后会在此会话回复（工单 #{handover.id}）</span>
            </div>
          )}
          <div className="chat-input">
            <div className="input-toolbar">
              <button
                type="button"
                className="handover-btn"
                onClick={handleManualHandover}
                disabled={!!handover || loading}
              >
                <Headset size={15} />
                {handover ? '已转人工' : '转人工'}
              </button>
            </div>
            <div className="input-box">
              <textarea
                rows={1}
                value={input}
                placeholder="问问杭州，比如：西湖和灵隐寺一天怎么安排？"
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button
                type="button"
                className="send-btn"
                disabled={!input.trim() || loading}
                onClick={() => sendMessage()}
                aria-label="发送"
              >
                <Send size={17} />
              </button>
            </div>
          </div>
        </main>

        <aside className="side-panel">
          <div className="panel-tabs">
            <button
              type="button"
              className={`panel-tab ${activeTab === '地图' ? 'active' : ''}`}
              onClick={() => setActiveTab('地图')}
            >
              <MapIcon size={15} /> 地图
            </button>
            <button
              type="button"
              className={`panel-tab ${activeTab === '行程' ? 'active' : ''}`}
              onClick={() => setActiveTab('行程')}
            >
              <Compass size={15} /> 行程
            </button>
            <button
              type="button"
              className={`panel-tab ${activeTab === '来源' ? 'active' : ''}`}
              onClick={() => setActiveTab('来源')}
            >
              <Database size={15} /> 来源
            </button>
          </div>
          <div className="panel-content">
            {activeTab === '地图' && (
              <MapView
                attractions={visibleAttractions}
                itinerary={lastResponse?.itinerary}
                scenicName={scenicAreas.find((area) => area.code === selectedScenic)?.name || ''}
                pois={visiblePois}
                showDetailed={showDetailed}
              />
            )}
            {activeTab === '行程' &&
              (lastResponse?.itinerary ? (
                <ItineraryTimeline itinerary={lastResponse.itinerary} />
              ) : (
                <EmptyPanel icon={Compass} text="问我路线后，这里会展示带时间的行程安排。" />
              ))}
            {activeTab === '来源' && (
              <SourceList sources={lastResponse?.sources || []} ticketHits={lastResponse?.ticket_hits || []} />
            )}
          </div>
        </aside>
      </div>
      {confirmDeleteId != null && (
        <div className="rating-mask">
          <div className="rating-card confirm-card">
            <h3>删除对话</h3>
            <p className="confirm-text">确认删除这个对话吗？删除后不可恢复。</p>
            <div className="confirm-actions">
              <button type="button" className="confirm-cancel" onClick={() => setConfirmDeleteId(null)}>
                取消
              </button>
              <button type="button" className="confirm-ok" onClick={doDeleteSession}>
                删除
              </button>
            </div>
          </div>
        </div>
      )}
      {showRating && (
        <div className="rating-mask">
          <div className="rating-card">
            <h3>本次人工服务体验如何？</h3>
            <div className="rating-stars">
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  type="button"
                  key={value}
                  className={value <= rating ? 'active' : ''}
                  onClick={() => setRating(value)}
                >
                  ★
                </button>
              ))}
            </div>
            <input
              type="text"
              value={ratingComment}
              placeholder="补充评价（可选）"
              onChange={(event) => setRatingComment(event.target.value)}
            />
            <button
              type="button"
              className="rating-submit"
              onClick={handleRateSubmit}
              disabled={rating < 1}
            >
              提交评价
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
