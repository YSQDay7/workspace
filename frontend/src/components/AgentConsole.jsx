import { useEffect, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ClipboardList,
  Headset,
  LogOut,
  MessageSquare,
  Pause,
  Play,
  RotateCcw,
  Search,
  Send,
  Star,
  Trash2,
  UserPlus,
  Users,
  Waves,
} from 'lucide-react';
import {
  adminAssignTicket,
  agentHeartbeat,
  closeAgentTicket,
  createAdminUser,
  deleteAdminUser,
  deleteAdminTicket,
  fetchAgentContext,
  fetchAgentPerformance,
  fetchAgentStatus,
  fetchAgentTasks,
  fetchMyRating,
  fetchNextWorkNo,
  fetchPendingTickets,
  fetchRecycleBin,
  fetchAdminUsers,
  restoreAdminUser,
  returnAgentTicket,
  sendAgentMessage,
  setAgentStatus as apiSetAgentStatus,
} from '../api';

const STATUS_LABELS = {
  queued: '排队中',
  assigned: '待处理',
  in_progress: '处理中',
  returned: '已转回',
  closed: '已关闭',
};

function waitText(seconds) {
  if (!seconds) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return `${seconds} 秒`;
  if (minutes < 60) return `${minutes} 分钟`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function TicketItem({ ticket, active, onSelect }) {
  return (
    <button type="button" className={`agent-ticket ${active ? 'active' : ''}`} onClick={() => onSelect(ticket.id)}>
      <div className="agent-ticket-top">
        <span className={`ticket-status ${ticket.status}`}>{STATUS_LABELS[ticket.status] || ticket.status}</span>
        <span className="ticket-priority">等待 {waitText(ticket.wait_seconds)}</span>
      </div>
      <p>{ticket.preview || ticket.reason || '暂无内容'}</p>
      <small>会话 #{ticket.session_id} · {ticket.user_name || '游客'}</small>
    </button>
  );
}

function MessageBubble({ message }) {
  if (message.sender_type === 'system') {
    return <div className="agent-system-note">{message.content}</div>;
  }
  const isUser = message.role === 'user';
  const isAgent = message.sender_type === 'agent';
  return (
    <div className={`agent-msg ${isUser ? 'user' : 'assistant'}`}>
      <span className="avatar small">{isUser ? '用' : isAgent ? '客' : <Bot size={14} />}</span>
      <div className="agent-msg-body">
        {isAgent && <strong>人工客服</strong>}
        <p>{message.content}</p>
      </div>
    </div>
  );
}

export default function AgentConsole({ user, onLogout }) {
  const isAdmin = user.role === 'admin';
  const [tab, setTab] = useState(isAdmin ? 'dispatch' : 'tasks');
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [context, setContext] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [rating, setRating] = useState(null);
  const [agentStatus, setAgentStatus] = useState('offline');
  const [pending, setPending] = useState({ count: 0, tickets: [] });
  const [performance, setPerformance] = useState([]);
  const [users, setUsers] = useState([]);
  const [recycle, setRecycle] = useState([]);
  const [filterRole, setFilterRole] = useState('');
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [userForm, setUserForm] = useState({
    username: '',
    password: '',
    role: 'customer_service',
    mobile: '',
  });
  const [error, setError] = useState('');

  async function loadTasks() {
    try {
      const data = await fetchAgentTasks();
      setTasks(data.tickets || []);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadRating() {
    try {
      const data = await fetchMyRating();
      setRating(data.rating);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadPending() {
    try {
      const data = await fetchPendingTickets();
      setPending(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadPerformance() {
    try {
      const data = await fetchAgentPerformance();
      setPerformance(data.agents || []);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadUsers() {
    try {
      const data = await fetchAdminUsers(filterRole || undefined, keyword || undefined);
      setUsers(data.users || []);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadRecycle() {
    try {
      const data = await fetchRecycleBin();
      setRecycle(data.users || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    if (isAdmin) {
      loadPending();
      loadPerformance();
      loadUsers();
      loadRecycle();
      const timer = setInterval(() => {
        loadPending();
        loadPerformance();
      }, 5000);
      return () => clearInterval(timer);
    }
    fetchAgentStatus()
      .then((data) => {
        if (data.status === 'offline') {
          return apiSetAgentStatus('online').then(() => setAgentStatus('online'));
        }
        setAgentStatus(data.status);
        return Promise.resolve();
      })
      .catch(() => apiSetAgentStatus('online').then(() => setAgentStatus('online')));
    loadTasks();
    loadRating();
    const timer = setInterval(() => {
      loadTasks();
    }, 5000);
    const heartbeat = setInterval(() => {
      agentHeartbeat().catch(() => {});
    }, 30000);
    agentHeartbeat().catch(() => {});
    return () => {
      clearInterval(timer);
      clearInterval(heartbeat);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return undefined;
    async function load() {
      try {
        const data = await fetchAgentContext(selectedId);
        setContext(data);
      } catch (err) {
        setError(err.message);
      }
    }
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [selectedId]);

  async function handleLeave() {
    const next = agentStatus === 'online' ? 'away' : 'online';
    try {
      await apiSetAgentStatus(next);
      setAgentStatus(next);
      loadTasks();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSend() {
    if (!selectedId || !replyText.trim()) return;
    try {
      await sendAgentMessage(selectedId, replyText);
      setReplyText('');
      const data = await fetchAgentContext(selectedId);
      setContext(data);
      await loadTasks();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleClose(ticketId) {
    try {
      await closeAgentTicket(ticketId);
      setContext(null);
      setSelectedId(null);
      await loadTasks();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleReturn(ticketId) {
    try {
      await returnAgentTicket(ticketId);
      setContext(null);
      setSelectedId(null);
      await loadTasks();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCreateUser(event) {
    event.preventDefault();
    setError('');
    const roleLabel = userForm.role === 'admin' ? 'AD 管理员' : userForm.role === 'customer_service' ? 'CS 客服' : '普通用户';
    if (userForm.role !== 'user' && !window.confirm(`账号用户名格式满足${roleLabel}身份，是否创建？`)) {
      return;
    }
    try {
      await createAdminUser(userForm);
      setUserForm({ username: '', password: '', role: 'customer_service', mobile: '' });
      await loadUsers();
      await loadPerformance();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteUser(target) {
    if (target.id === user.id) return;
    const confirmed = window.confirm(`确认删除账号 ${target.work_no || target.username} 吗？删除后进入回收站。`);
    if (!confirmed) return;
    try {
      await deleteAdminUser(target.id);
      await loadUsers();
      await loadRecycle();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRestore(target) {
    try {
      await restoreAdminUser(target.id);
      await loadUsers();
      await loadRecycle();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRoleChange(role) {
    setUserForm({ ...userForm, role });
    if (role === 'user') return;
    try {
      const data = await fetchNextWorkNo(role);
      setUserForm((prev) => ({ ...prev, role, username: data.work_no }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAssign(ticketId, agentId) {
    try {
      await adminAssignTicket(ticketId, agentId);
      await loadPending();
      await loadPerformance();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteTicket(ticketId) {
    const confirmed = window.confirm('确认删除这个工单吗？删除后不可恢复。');
    if (!confirmed) return;
    try {
      await deleteAdminTicket(ticketId);
      await loadPending();
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    if (!isAdmin) return undefined;
    loadUsers();
    loadRecycle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterRole, keyword, isAdmin]);

  async function handleUserSearch(event) {
    event?.preventDefault();
    setKeyword(keywordInput.trim());
  }

  const selectedTicket = tasks.find((ticket) => ticket.id === selectedId);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark"><Headset size={20} /></span>
          <div>
            <h1>客服工作台</h1>
            <p>{user.work_no || user.username} · {isAdmin ? '管理员' : '客服'}</p>
          </div>
        </div>
        <div className="header-right">
          {!isAdmin && (
            <button type="button" className={`agent-leave-btn ${agentStatus === 'away' ? 'away' : ''}`} onClick={handleLeave}>
              {agentStatus === 'away' ? <Play size={14} /> : <Pause size={14} />}
              {agentStatus === 'away' ? '返回在线' : '离开'}
            </button>
          )}
          <button type="button" className="header-logout" onClick={onLogout} title="退出登录">
            <LogOut size={15} />
          </button>
        </div>
      </header>

      <div className="agent-console">
        <div className="agent-tabs">
          {isAdmin ? (
            <>
              <button type="button" className={tab === 'dispatch' ? 'active' : ''} onClick={() => setTab('dispatch')}>
                <ClipboardList size={15} /> 调度台
              </button>
              <button type="button" className={tab === 'performance' ? 'active' : ''} onClick={() => setTab('performance')}>
                <Users size={15} /> 客服绩效
              </button>
              <button type="button" className={tab === 'accounts' ? 'active' : ''} onClick={() => setTab('accounts')}>
                <UserPlus size={15} /> 账号管理
              </button>
              <button type="button" className={tab === 'recycle' ? 'active' : ''} onClick={() => setTab('recycle')}>
                <Trash2 size={15} /> 回收站
              </button>
            </>
          ) : (
            <>
              <button type="button" className={tab === 'tasks' ? 'active' : ''} onClick={() => setTab('tasks')}>
                <MessageSquare size={15} /> 我的任务
              </button>
              <button type="button" className={tab === 'rating' ? 'active' : ''} onClick={() => { setTab('rating'); loadRating(); }}>
                <Star size={15} /> 我的评分
              </button>
            </>
          )}
        </div>

        {error && <div className="agent-error">{error}</div>}

        {!isAdmin && tab === 'tasks' && (
          <div className="agent-queue">
            <aside className="agent-ticket-list">
              <h3>待办任务（{tasks.length}）</h3>
              <div className="agent-ticket-scroll">
                {tasks.map((ticket) => (
                  <TicketItem
                    key={ticket.id}
                    ticket={ticket}
                    active={ticket.id === selectedId}
                    onSelect={(id) => setSelectedId(id)}
                  />
                ))}
                {tasks.length === 0 && <p className="agent-empty">暂无待办任务</p>}
              </div>
            </aside>
            <section className="agent-chat">
              {context ? (
                <>
                  <div className="agent-chat-head">
                    <div>
                      <strong>会话 #{context.ticket.session_id}</strong>
                      <span>{context.ticket.reason || ''}</span>
                    </div>
                    <div className="agent-chat-actions">
                      <button type="button" onClick={() => handleReturn(context.ticket.id)}>
                        <RotateCcw size={14} /> 转回机器人
                      </button>
                      <button type="button" className="close" onClick={() => handleClose(context.ticket.id)}>
                        <CheckCircle2 size={14} /> 结束会话
                      </button>
                    </div>
                  </div>
                  <div className="agent-chat-scroll">
                    {(context.messages || []).map((message) => (
                      <MessageBubble key={message.id} message={message} />
                    ))}
                  </div>
                  <div className="agent-reply">
                    <textarea
                      rows={2}
                      value={replyText}
                      placeholder="输入回复内容..."
                      onChange={(event) => setReplyText(event.target.value)}
                    />
                    <button type="button" onClick={handleSend} disabled={!replyText.trim()}>
                      <Send size={15} /> 发送
                    </button>
                  </div>
                </>
              ) : (
                <div className="agent-empty-large">
                  <MessageSquare size={32} />
                  <p>选择一条任务开始接待</p>
                </div>
              )}
            </section>
          </div>
        )}

        {!isAdmin && tab === 'rating' && (
          <div className="agent-stats">
            <div className="stat-card"><strong>{rating?.average ?? '-'}</strong><span>平均评分</span></div>
            <div className="stat-card"><strong>{rating?.count ?? 0}</strong><span>评价数量</span></div>
            <div className="stat-card"><strong>{agentStatus === 'online' ? '在线' : agentStatus === 'away' ? '离开中' : '离线'}</strong><span>当前状态</span></div>
            <div className="rating-recent">
              <h3>最近评价</h3>
              {(rating?.recent || []).map((item, index) => (
                <div className="rating-recent-row" key={index}>
                  <span>{'★'.repeat(item.score)}</span>
                  <p>{item.comment || '无备注'}</p>
                </div>
              ))}
              {!rating?.recent?.length && <p className="agent-empty">暂无评价</p>}
            </div>
          </div>
        )}

        {isAdmin && tab === 'dispatch' && (
          <div className="admin-dispatch">
            <div className="admin-section-head">
              <h3>待分配转人工请求（{pending.count}）</h3>
            </div>
            <div className="dispatch-list">
              {pending.tickets.map((ticket) => (
                <div className="dispatch-row" key={ticket.id}>
                  <div>
                    <strong>工单 #{ticket.id}</strong>
                    <p>{ticket.preview || ticket.reason}</p>
                    <small>等待 {waitText(ticket.wait_seconds)} · 会话 #{ticket.session_id}</small>
                  </div>
                  <div className="dispatch-actions">
                    <select
                      defaultValue=""
                      onChange={(event) => handleAssign(ticket.id, Number(event.target.value))}
                    >
                      <option value="" disabled>选择客服分配</option>
                      {performance
                        .filter((item) => item.status !== 'away' && item.status !== 'offline')
                        .map((item) => (
                          <option key={item.user_id} value={item.user_id}>
                            {item.work_no}（在线）
                          </option>
                        ))}
                    </select>
                    <button type="button" className="dispatch-delete-btn" onClick={() => handleDeleteTicket(ticket.id)}>
                      <Trash2 size={13} /> 删除
                    </button>
                  </div>
                </div>
              ))}
              {pending.tickets.length === 0 && <p className="agent-empty">暂无待分配请求</p>}
            </div>
          </div>
        )}

        {isAdmin && tab === 'performance' && (
          <div className="admin-performance">
            <table className="perf-table">
              <thead>
                <tr>
                  <th>工号</th>
                  <th>状态</th>
                  <th>离开时长</th>
                  <th>平均评分</th>
                  <th>评价数</th>
                  <th>今日接待</th>
                  <th>处理中</th>
                </tr>
              </thead>
              <tbody>
                {performance.map((item) => (
                  <tr key={item.user_id}>
                    <td>{item.work_no}</td>
                    <td>{item.status === 'online' ? '在线' : item.status === 'away' ? '离开中' : '离线'}</td>
                    <td>{item.status === 'away' ? `${item.away_minutes} 分钟` : '-'}</td>
                    <td>{item.average_rating ?? '-'}</td>
                    <td>{item.rating_count}</td>
                    <td>{item.today}</td>
                    <td>{item.active}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {isAdmin && tab === 'accounts' && (
          <div className="agent-admin">
            <section className="admin-create">
              <h3>创建账号</h3>
              <form onSubmit={handleCreateUser}>
                <select value={userForm.role} onChange={(event) => handleRoleChange(event.target.value)}>
                  <option value="customer_service">客服（CS 工号）</option>
                  <option value="admin">管理员（AD 工号）</option>
                  <option value="user">普通用户</option>
                </select>
                <input
                  type="text"
                  placeholder={userForm.role === 'user' ? '用户名' : '工号（自动生成）'}
                  value={userForm.username}
                  onChange={(event) => setUserForm({ ...userForm, username: event.target.value })}
                />
                <input
                  type="password"
                  placeholder="密码（至少 6 位）"
                  value={userForm.password}
                  onChange={(event) => setUserForm({ ...userForm, password: event.target.value })}
                />
                <button type="submit"><UserPlus size={15} /> 创建</button>
              </form>
            </section>
            <section className="admin-users">
              <div className="admin-filter-bar">
                <h3>账号列表</h3>
                <select value={filterRole} onChange={(event) => setFilterRole(event.target.value)}>
                  <option value="">全部</option>
                  <option value="user">普通用户</option>
                  <option value="customer_service">客服</option>
                  <option value="admin">管理员</option>
                </select>
                <div className="admin-search">
                  <Search size={14} />
                  <input
                    type="text"
                    placeholder="输入用户名/工号"
                    value={keywordInput}
                    onChange={(event) => setKeywordInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') handleUserSearch();
                    }}
                  />
                  <button type="button" className="query-btn" onClick={handleUserSearch}>
                    查询
                  </button>
                </div>
              </div>
              <div className="admin-user-row head"><span>用户名</span><span>角色</span><span>创建时间</span><span></span></div>
              {users.map((item) => (
                <div className="admin-user-row" key={item.id}>
                  <span>{item.work_no || item.username}</span>
                  <span>{item.role === 'admin' ? '管理员' : item.role === 'customer_service' ? '客服' : '普通用户'}</span>
                  <span>{new Date(item.created_at).toLocaleDateString('zh-CN')}</span>
                  {item.id !== user.id && (
                    <button type="button" className="admin-delete-btn" onClick={() => handleDeleteUser(item)}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              ))}
            </section>
          </div>
        )}

        {isAdmin && tab === 'recycle' && (
          <div className="admin-recycle">
            <h3>回收站（删除后 3 天内可恢复）</h3>
            <div className="admin-user-row head"><span>用户名</span><span>原身份</span><span>删除时间</span><span></span></div>
            {recycle.map((item) => (
              <div className="admin-user-row" key={item.id}>
                <span>{item.work_no || item.username}</span>
                <span>{item.original_role === 'admin' ? '管理员' : item.original_role === 'customer_service' ? '客服' : '普通用户'}</span>
                <span>{item.deleted_at ? new Date(item.deleted_at).toLocaleString('zh-CN') : '-'}</span>
                <button type="button" className="restore-btn" onClick={() => handleRestore(item)}>
                  <RotateCcw size={13} /> 恢复
                </button>
              </div>
            ))}
            {recycle.length === 0 && <p className="agent-empty">回收站为空</p>}
          </div>
        )}
      </div>
    </div>
  );
}
