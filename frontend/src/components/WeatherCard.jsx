import { Cloud, CloudFog, CloudRain, CloudSun, Droplets, Sun, Wind } from 'lucide-react';

function WeatherIcon({ description }) {
  if (!description) return <CloudSun size={18} />;
  if (description.includes('雨')) return <CloudRain size={18} />;
  if (description.includes('云') || description.includes('阴')) return <Cloud size={18} />;
  if (description.includes('雾')) return <CloudFog size={18} />;
  return <Sun size={18} />;
}

function formatDay(dateString) {
  const date = new Date(`${dateString}T00:00:00`);
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', weekday: 'short' });
}

export default function WeatherCard({ weather }) {
  if (!weather) {
    return (
      <section className="weather-card">
        <h3>杭州天气</h3>
        <p className="weather-empty">正在获取实时天气...</p>
      </section>
    );
  }
  const current = weather.current || {};
  return (
    <section className="weather-card">
      <div className="weather-head">
        <div>
          <h3>杭州天气</h3>
          <span className="weather-source">{weather.source === 'mock' ? '预报数据' : '实时数据'}</span>
        </div>
        <WeatherIcon description={current.description} />
      </div>
      <div className="weather-current">
        <span className="weather-temp">{Math.round(current.temperature)}°</span>
        <div className="weather-now">
          <strong>{current.description}</strong>
          <span>体感 {Math.round(current.apparent_temperature)}°C</span>
        </div>
      </div>
      <div className="weather-meta">
        <span><Droplets size={13} /> 湿度 {current.humidity}%</span>
        <span><Wind size={13} /> 风速 {current.wind_speed} km/h</span>
      </div>
      <div className="weather-days">
        {(weather.daily || []).map((day) => (
          <div className="weather-day" key={day.date}>
            <span className="weather-day-name">{formatDay(day.date)}</span>
            <WeatherIcon description={day.description} />
            <span className="weather-day-desc">{day.description}</span>
            <span className="weather-day-temp">
              {Math.round(day.temp_min)}° / {Math.round(day.temp_max)}°
            </span>
            <span className="weather-day-rain">{day.precipitation_probability}%</span>
          </div>
        ))}
      </div>
    </section>
  );
}
