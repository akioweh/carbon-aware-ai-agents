"use client"

import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet"

export interface DatacenterMapPoint {
  id: string
  name: string
  regionId: number
  latitude: number
  longitude: number
  active: boolean
}

interface DatacenterMapProps {
  centres: DatacenterMapPoint[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function getMarkerColor(active: boolean) {
  return active ? "#111827" : "#94a3b8"
}

export function DatacenterMap({ centres, selectedId, onSelect }: DatacenterMapProps) {
  return (
    <MapContainer
      center={[53.2, -2.2]}
      zoom={5.8}
      scrollWheelZoom={false}
      zoomControl={false}
      attributionControl={false}
      className="h-full w-full bg-stone-100"
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
      />

      {centres.map((dc) => {
        const isSelected = selectedId === dc.id

        return (
          <CircleMarker
            key={dc.id}
            center={[dc.latitude, dc.longitude]}
            radius={isSelected ? 11 : 8}
            pathOptions={{
              color: "#ffffff",
              weight: isSelected ? 3 : 2,
              fillColor: getMarkerColor(dc.active),
              fillOpacity: 1,
            }}
            eventHandlers={{ click: () => onSelect(dc.id) }}
          >
            <Tooltip direction="top" offset={[0, -12]} opacity={0.98} permanent={false}>
              <div className="space-y-1">
                <div className="text-[12px] font-semibold leading-none">{dc.id}</div>
                <div className="text-[12px] leading-none">{dc.name}</div>
                <div className="text-[11px] text-slate-500 leading-none">
                  Region {dc.regionId} · {dc.active ? "Enabled" : "Disabled"}
                </div>
              </div>
            </Tooltip>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}