import { CalendarClock, Clock, MapPin, Timer } from 'lucide-react';

export default function ItineraryTimeline({ itinerary }) {
  const stops = itinerary?.stops || [];
  return (
    <div className="itinerary">
      <div className="itinerary-head">
        <div className="itinerary-title">
          <CalendarClock size={18} />
          <div>
            <h3>{itinerary?.title}</h3>
            <p>{itinerary?.summary}</p>
          </div>
        </div>
        <div className="itinerary-meta">
          <span><Clock size={14} /> {itinerary?.start_time} - {itinerary?.end_time}</span>
          <span><Timer size={14} /> 约 {itinerary?.total_hours} 小时</span>
        </div>
      </div>
      <div className="timeline">
        {stops.map((stop, index) => (
          <div className="timeline-item" key={`${stop.name}-${index}`}>
            <div className="timeline-rail">
              <span className="timeline-dot">{index + 1}</span>
              {index < stops.length - 1 && <span className="timeline-line" />}
            </div>
            <div className="timeline-card">
              <div className="timeline-card-top">
                <span className="time-pill">{stop.time}</span>
                <strong>{stop.name}</strong>
                <span className="duration-pill">{stop.duration_minutes} 分钟</span>
              </div>
              <p>{stop.description}</p>
              {stop.tips && (
                <div className="timeline-tip">
                  <MapPin size={12} />
                  <span>{stop.tips}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

