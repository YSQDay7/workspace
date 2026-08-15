import { useEffect, useRef } from 'react';
import { MapPin, Route } from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const AMAP_SUBDOMAINS = ['01', '02', '03', '04'];

function attractionIcon() {
  return L.divIcon({
    className: '',
    html: '<div class="map-pin attraction"><span class="pin-dot"></span></div>',
    iconSize: [26, 32],
    iconAnchor: [13, 30],
    popupAnchor: [0, -28],
  });
}

function routeIcon(index) {
  return L.divIcon({
    className: '',
    html: `<div class="map-pin route">${index}</div>`,
    iconSize: [28, 34],
    iconAnchor: [14, 32],
    popupAnchor: [0, -30],
  });
}

function popupHtml(title, subtitle) {
  return `<div class="wl-popup"><strong>${title}</strong><span>${subtitle}</span></div>`;
}

export default function MapView({ attractions = [], itinerary = null, scenicName = '', pois = [], showDetailed = true }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      scrollWheelZoom: true,
      attributionControl: true,
    });

    const amapNormal = L.tileLayer(
      'https://webrd{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      {
        maxZoom: 18,
        subdomains: AMAP_SUBDOMAINS,
        attribution: '&copy; 高德地图',
      },
    );
    const amapSatellite = L.layerGroup([
      L.tileLayer('https://webst{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}', {
        maxZoom: 18,
        subdomains: AMAP_SUBDOMAINS,
      }),
      L.tileLayer('https://webst{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}', {
        maxZoom: 18,
        subdomains: AMAP_SUBDOMAINS,
        opacity: 0.9,
      }),
    ]);
    const esriTopo = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 17,
        attribution: 'Tiles &copy; Esri',
      },
    );

    amapNormal.addTo(map);
    L.control
      .layers({ 标准地图: amapNormal, 卫星影像: amapSatellite, 地形图: esriTopo }, null, {
        position: 'topright',
        collapsed: true,
      })
      .addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false, metric: true }).addTo(map);
    map.setView([30.25, 120.16], 11);

    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();

    const points = [];
    itinerary?.stops?.forEach((stop, index) => {
      if (!stop.latitude || !stop.longitude) return;
      points.push([stop.latitude, stop.longitude]);
      const marker = L.marker([stop.latitude, stop.longitude], { icon: routeIcon(index + 1) });
      marker.bindTooltip(`${stop.time} ${stop.name}`, {
        direction: 'top',
        offset: [0, -30],
        opacity: 0.94,
      });
      marker.bindPopup(popupHtml(`${stop.time} ${stop.name}`, stop.description), {
        maxWidth: 250,
        className: 'wl-popup-shell',
      });
      layer.addLayer(marker);
    });

    if (points.length >= 2) {
      L.polyline(points, {
        color: '#e2574c',
        weight: 4,
        opacity: 0.9,
        dashArray: '8 8',
      }).addTo(layer);
    }

    if (showDetailed) {
      (pois || []).forEach((item) => {
        if (!item.latitude || !item.longitude) return;
        const marker = L.marker([item.latitude, item.longitude], { icon: attractionIcon() });
        marker.bindTooltip(item.name, { direction: 'top', offset: [0, -28], opacity: 0.92 });
        marker.bindPopup(
          popupHtml(item.name, `${item.category} · ${item.tips || ''}`),
          { maxWidth: 250, className: 'wl-popup-shell' },
        );
        layer.addLayer(marker);
      });
    }

    attractions.forEach((item) => {
      if (!item.latitude || !item.longitude) return;
      const marker = L.marker([item.latitude, item.longitude], { icon: attractionIcon() });
      marker.bindTooltip(item.name, { direction: 'top', offset: [0, -28], opacity: 0.92 });
      marker.bindPopup(
        popupHtml(item.name, `${item.category} · ${item.intro}`),
        { maxWidth: 250, className: 'wl-popup-shell' },
      );
      layer.addLayer(marker);
    });

    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points).pad(0.35));
    } else if (attractions.length > 0) {
      const bounds = L.latLngBounds(
        attractions.filter((a) => a.latitude && a.longitude).map((a) => [a.latitude, a.longitude]),
      );
      map.fitBounds(bounds.pad(0.12));
    } else {
      map.setView([30.25, 120.16], 11);
    }
  }, [attractions, itinerary]);

  return (
    <div className="map-shell">
      <div className="map-wrap" ref={containerRef} />
      <div className="map-overlay">
        {itinerary ? (
          <>
            <span className="map-overlay-badge">
              <Route size={12} /> {showDetailed ? '行程路线' : '全城关键节点'}
            </span>
            <strong>{itinerary.title}</strong>
            <small>
              {itinerary.start_time} - {itinerary.end_time} · 约 {itinerary.total_hours} 小时 ·{' '}
              {itinerary.stops.length} 站
              {!showDetailed && ' · 仅显示主要景区'}
            </small>
          </>
        ) : (
          <>
            <span className="map-overlay-badge"><MapPin size={12} /> {scenicName || '杭州景区'}</span>
            <strong>{attractions.length} 个景点标记</strong>
            <small>点击标点查看介绍，右上角可切换底图</small>
          </>
        )}
      </div>
    </div>
  );
}
