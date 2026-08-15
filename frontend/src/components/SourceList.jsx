import { Cloud, Database, MapPin, Ticket } from 'lucide-react';

function TypeIcon({ type }) {
  if (type === 'weather') return <Cloud size={14} />;
  if (type === 'ticket') return <Ticket size={14} />;
  if (type === 'route') return <MapPin size={14} />;
  return <Database size={14} />;
}

export default function SourceList({ sources = [], ticketHits = [] }) {
  const hasData = sources.length > 0 || ticketHits.length > 0;
  if (!hasData) {
    return (
      <div className="panel-empty">
        <Database size={28} />
        <p>问答后，这里会展示答案引用的知识库和工具来源。</p>
      </div>
    );
  }
  return (
    <div className="source-list">
      {ticketHits.map((ticket) => (
        <article className="source-card ticket-card" key={ticket.name}>
          <div className="source-card-head">
            <span className="source-type ticket"><Ticket size={13} /> 票务数据</span>
            <strong>{ticket.name}</strong>
          </div>
          <div className="ticket-facts">
            <span>价格 {ticket.price}</span>
            <span>{ticket.opening_hours}</span>
          </div>
          <p>{ticket.price_note}</p>
        </article>
      ))}
      {sources.map((source, index) => (
        <article className="source-card" key={`${source.title}-${index}`}>
          <div className="source-card-head">
            <span className={`source-type ${source.metadata?.type || 'knowledge'}`}>
              <TypeIcon type={source.metadata?.type} /> {source.category}
            </span>
            {typeof source.score === 'number' && <span className="source-score">{Math.round(source.score * 100)}%</span>}
          </div>
          <strong>{source.title}</strong>
          <p>{source.snippet}</p>
        </article>
      ))}
    </div>
  );
}
