/**
 * ShopGuard Dashboard — server component, revalidates every 30 s.
 *
 * Reads alerts and heartbeat directly from Supabase.
 * RLS ensures users see only their own store's data.
 * Unauthenticated users are redirected to /login.
 */

import { redirect } from 'next/navigation'
import type { SupabaseClient } from '@supabase/supabase-js'
import type { Alert, Heartbeat } from '@/lib/supabase'
import { isOnline } from '@/lib/supabase'
import { createSupabaseServer } from '@/lib/supabase-server'
import LogoutButton from '@/app/components/LogoutButton'

export const revalidate = 30

async function getAlerts(supabase: SupabaseClient): Promise<Alert[]> {
  const { data, error } = await supabase
    .from('alerts')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(50)
  if (error) console.error('alerts fetch error:', error.message)
  return data ?? []
}

async function getHeartbeat(supabase: SupabaseClient): Promise<Heartbeat | null> {
  const { data, error } = await supabase
    .from('heartbeats')
    .select('*')
    .single()
  // PGRST116 = no rows — expected when agent hasn't connected yet
  if (error && error.code !== 'PGRST116') {
    console.error('heartbeat fetch error:', error.message)
  }
  return data ?? null
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const ALERT_TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  zone_violation: { bg: '#dc2626', text: '#fff' },
  loitering: { bg: '#ea580c', text: '#fff' },
  pacing: { bg: '#ca8a04', text: '#fff' },
  overcrowded: { bg: '#9333ea', text: '#fff' },
}

const ZONE_COLORS = ['#6366f1', '#0ea5e9', '#14b8a6', '#f59e0b', '#ec4899', '#8b5cf6']

function getZoneColor(zoneName: string): string {
  let hash = 0
  for (let i = 0; i < zoneName.length; i++) {
    hash = zoneName.charCodeAt(i) + ((hash << 5) - hash)
  }
  return ZONE_COLORS[Math.abs(hash) % ZONE_COLORS.length]
}

/* ── Shared styles ── */

const card: React.CSSProperties = {
  background: '#1a1f2e',
  borderRadius: 12,
  border: '1px solid #2a3042',
}

const sectionTitle: React.CSSProperties = {
  fontSize: '0.75rem',
  fontWeight: 600,
  letterSpacing: '0.05em',
  color: '#64748b',
  textTransform: 'uppercase' as const,
  marginBottom: '0.75rem',
}

export default async function DashboardPage() {
  const supabase = await createSupabaseServer()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) redirect('/login')

  const [alerts, heartbeat] = await Promise.all([
    getAlerts(supabase),
    getHeartbeat(supabase),
  ])
  const online = isOnline(heartbeat)

  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const oneHourAgo = new Date(now.getTime() - 3_600_000)

  const alertsToday = alerts.filter((a) => new Date(a.created_at) >= todayStart).length
  const alertsLastHour = alerts.filter((a) => new Date(a.created_at) >= oneHourAgo).length

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem' }}>
      {/* ── Header ── */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '2rem',
          paddingBottom: '1.25rem',
          borderBottom: '1px solid #1e2433',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Logo */}
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.1rem',
              fontWeight: 800,
              color: '#fff',
              flexShrink: 0,
            }}
          >
            S
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>
            ShopGuard
          </span>
          {/* Online/offline badge */}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.75rem',
              fontWeight: 500,
              padding: '2px 10px',
              borderRadius: 999,
              background: online ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
              color: online ? '#4ade80' : '#f87171',
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: online ? '#22c55e' : '#ef4444',
              }}
            />
            {online ? 'Online' : 'Offline'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ color: '#64748b', fontSize: '0.8rem' }}>{user.email}</span>
          <LogoutButton />
        </div>
      </header>

      {/* ── Stats row ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '0.75rem',
          marginBottom: '2rem',
        }}
      >
        <StatCard label="Alerts Today" value={alertsToday} accent={alertsToday > 0 ? '#f59e0b' : '#4ade80'} />
        <StatCard label="Last Hour" value={alertsLastHour} accent={alertsLastHour > 0 ? '#f59e0b' : '#4ade80'} />
        <StatCard
          label="Store Status"
          value={heartbeat ? (online ? 'Online' : 'Offline') : 'N/A'}
          accent={online ? '#22c55e' : '#ef4444'}
        />
        <StatCard
          label="Last Heartbeat"
          value={heartbeat ? formatRelativeTime(heartbeat.last_seen) : 'Never'}
          accent="#8b5cf6"
        />
      </div>

      {/* ── Alert feed ── */}
      <section>
        <h2 style={sectionTitle}>Recent Alerts</h2>

        {alerts.length === 0 ? (
          <div
            style={{
              ...card,
              padding: '3rem 2rem',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem', opacity: 0.4 }}>
              &#x1F6E1;
            </div>
            <p style={{ color: '#94a3b8', fontSize: '1rem', margin: 0, fontWeight: 500 }}>
              No alerts yet
            </p>
            <p style={{ color: '#475569', fontSize: '0.85rem', margin: '0.5rem 0 0' }}>
              Alerts will appear here when suspicious activity is detected.
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {alerts.map((alert) => {
              const typeStyle = alert.alert_type
                ? ALERT_TYPE_COLORS[alert.alert_type] ?? { bg: '#475569', text: '#fff' }
                : null
              const zoneColor = alert.zone_name ? getZoneColor(alert.zone_name) : '#475569'

              return (
                <div
                  key={alert.id}
                  style={{
                    ...card,
                    padding: '0.875rem 1rem',
                    display: 'flex',
                    gap: '0.875rem',
                    alignItems: 'center',
                  }}
                >
                  {/* Thumbnail */}
                  {alert.image_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={alert.image_url}
                      alt="Alert frame"
                      style={{
                        width: 100,
                        height: 64,
                        objectFit: 'cover',
                        borderRadius: 8,
                        flexShrink: 0,
                        background: '#111520',
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: 100,
                        height: 64,
                        borderRadius: 8,
                        flexShrink: 0,
                        background: '#111520',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#334155',
                        fontSize: '0.7rem',
                      }}
                    >
                      No image
                    </div>
                  )}

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        display: 'flex',
                        gap: '0.4rem',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        marginBottom: 4,
                      }}
                    >
                      {/* Alert type badge */}
                      {alert.alert_type && typeStyle && (
                        <span
                          style={{
                            background: typeStyle.bg,
                            color: typeStyle.text,
                            borderRadius: 4,
                            padding: '1px 7px',
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            textTransform: 'uppercase' as const,
                            letterSpacing: '0.02em',
                          }}
                        >
                          {alert.alert_type.replace('_', ' ')}
                        </span>
                      )}
                      {/* Zone badge */}
                      <span
                        style={{
                          background: `${zoneColor}20`,
                          color: zoneColor,
                          borderRadius: 4,
                          padding: '1px 7px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                        }}
                      >
                        {alert.zone_name || 'unknown zone'}
                      </span>
                      {/* Camera */}
                      <span style={{ color: '#64748b', fontSize: '0.7rem' }}>
                        cam {alert.camera_index}
                      </span>
                    </div>
                    {/* Timestamp */}
                    <span style={{ color: '#475569', fontSize: '0.75rem' }}>
                      {formatTime(alert.created_at)}
                    </span>
                  </div>

                  {/* Relative time on right */}
                  <span
                    style={{
                      color: '#64748b',
                      fontSize: '0.75rem',
                      flexShrink: 0,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {formatRelativeTime(alert.created_at)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </main>
  )
}

/* ── Stat card component ── */

function StatCard({
  label,
  value,
  accent,
}: {
  label: string
  value: string | number
  accent: string
}) {
  return (
    <div
      style={{
        ...card,
        padding: '1rem 1.125rem',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Accent top bar */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: accent,
          borderRadius: '12px 12px 0 0',
        }}
      />
      <div style={{ fontSize: '0.7rem', fontWeight: 500, color: '#64748b', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: '0.04em' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>
        {value}
      </div>
    </div>
  )
}
