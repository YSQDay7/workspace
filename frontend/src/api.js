const TOKEN_KEY = 'hz_token';
const REFRESH_KEY = 'hz_refresh_token';
const USER_KEY = 'hz_user';
const SESSION_KEY = 'hz_session_id';
const GUEST_KEY = 'hz_guest';

export function webStorage() {
  try {
    return window.location.pathname === '/agent' ? window.sessionStorage : window.localStorage;
  } catch (error) {
    return window.localStorage;
  }
}

export function getToken() {
  try {
    return webStorage().getItem(TOKEN_KEY);
  } catch (error) {
    return null;
  }
}

export function setToken(token) {
  try {
    webStorage().setItem(TOKEN_KEY, token);
  } catch (error) {
    // ignore
  }
}

export function clearToken() {
  try {
    webStorage().removeItem(TOKEN_KEY);
  } catch (error) {
    // ignore
  }
}

let refreshTokenValue = null;

export function setRefreshToken(token) {
  refreshTokenValue = token;
  try {
    webStorage().setItem(REFRESH_KEY, token);
  } catch (error) {
    // ignore
  }
}

export function getRefreshToken() {
  if (refreshTokenValue) return refreshTokenValue;
  try {
    return webStorage().getItem(REFRESH_KEY);
  } catch (error) {
    return null;
  }
}

export function clearRefreshToken() {
  refreshTokenValue = null;
  try {
    webStorage().removeItem(REFRESH_KEY);
  } catch (error) {
    // ignore
  }
}

export { USER_KEY, SESSION_KEY, GUEST_KEY };

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(url, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeaders(),
    ...(options.headers || {}),
  };
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const data = await response.json();
      if (data.detail) detail = data.detail;
    } catch (error) {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return response.json();
}

export function getJson(url) {
  return request(url);
}

export function postJson(url, body) {
  return request(url, { method: 'POST', body: JSON.stringify(body || {}) });
}

export function deleteJson(url) {
  return request(url, { method: 'DELETE' });
}

export function fetchCaptcha() {
  return getJson('/api/auth/captcha');
}

export function register(payload) {
  return postJson('/api/auth/register', payload);
}

export function login(payload) {
  return postJson('/api/auth/login', payload);
}

export function logout() {
  return postJson('/api/auth/logout', {});
}

export async function refreshAccess() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      clearToken();
      return false;
    }
    const data = await response.json();
    setToken(data.token);
    return true;
  } catch (error) {
    return false;
  }
}

export function fetchSessions() {
  return getJson('/api/sessions');
}

export function createSession(title = '新对话') {
  return postJson('/api/sessions', { title });
}

export function fetchSessionMessages(sessionId) {
  return getJson(`/api/sessions/${sessionId}/messages`);
}

export function deleteSession(sessionId) {
  return deleteJson(`/api/sessions/${sessionId}`);
}

export function deleteMessage(messageId, sessionId) {
  return deleteJson(`/api/messages/${messageId}?session_id=${sessionId}`);
}

export function fetchHotQuestions() {
  return getJson('/api/hot-questions');
}

export async function streamChat(sessionId, question, scenicAreas, onEvent) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({ session_id: sessionId, question, scenic_areas: scenicAreas || null }),
  });
  if (!response.ok || !response.body) {
    let detail = `请求失败（${response.status}）`;
    try {
      const data = await response.json();
      if (data.detail) detail = data.detail;
    } catch (error) {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      let eventName = 'message';
      const dataLines = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length > 0) {
        try {
          onEvent(eventName, JSON.parse(dataLines.join('\n')));
        } catch (error) {
          // skip malformed event
        }
      }
    }
  }
}

export function createHandover(sessionId, reason) {
  return postJson('/api/agent/handover', { session_id: sessionId, reason: reason || '' });
}

export function fetchAgentTasks() {
  return getJson('/api/agent/tasks');
}

export function fetchAgentContext(ticketId) {
  return getJson(`/api/agent/tickets/${ticketId}/context`);
}

export function sendAgentMessage(ticketId, content) {
  return postJson('/api/agent/messages', { ticket_id: ticketId, content });
}

export function closeAgentTicket(ticketId, payload = {}) {
  return postJson(`/api/agent/tickets/${ticketId}/close`, payload);
}

export function returnAgentTicket(ticketId) {
  return postJson(`/api/agent/tickets/${ticketId}/return`, {});
}

export function rateTicket(ticketId, score, comment) {
  return postJson(`/api/agent/tickets/${ticketId}/rate`, { score, comment: comment || '' });
}

export function setAgentStatus(status) {
  return postJson('/api/agent/status', { status });
}

export function fetchAgentStatus() {
  return getJson('/api/agent/status');
}

export function agentHeartbeat() {
  return postJson('/api/agent/heartbeat', {});
}

export function fetchMyRating() {
  return getJson('/api/agent/my-rating');
}

export function fetchAdminUsers(role, keyword) {
  const params = new URLSearchParams();
  if (role) params.set('role', role);
  if (keyword) params.set('keyword', keyword);
  return getJson(`/api/admin/users?${params.toString()}`);
}

export function createAdminUser(payload) {
  return postJson('/api/admin/users', payload);
}

export function deleteAdminUser(userId) {
  return deleteJson(`/api/admin/users/${userId}`);
}

export function fetchRecycleBin() {
  return getJson('/api/admin/recycle-bin');
}

export function restoreAdminUser(userId) {
  return postJson(`/api/admin/users/${userId}/restore`, {});
}

export function fetchNextWorkNo(role) {
  return getJson(`/api/admin/next-work-no?role=${role}`);
}

export function fetchPendingTickets() {
  return getJson('/api/admin/pending-tickets');
}

export function adminAssignTicket(ticketId, agentId) {
  return postJson(`/api/admin/tickets/${ticketId}/assign`, { agent_id: agentId });
}

export function deleteAdminTicket(ticketId) {
  return deleteJson(`/api/admin/tickets/${ticketId}`);
}

export function fetchAgentPerformance() {
  return getJson('/api/admin/agent-performance');
}
