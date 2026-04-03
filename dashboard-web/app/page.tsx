/**
 * ShopGuard Dashboard — server component, revalidates every 30 s.
 *
 * Reads alerts and heartbeat directly from Supabase.
 * No backend server required.
 */

import { createClient } from '@supabase/supabase-js'
import type { Alert, Heartbeat } from '@/lib/supabase'
import { isOnline } from '@/lib/supabase'

export const revalidate = 30

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  )
}

async function getAlerts(): Promise<Alert[]> {
  const { data, error } = await getSupabase()
    .from('alerts')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(50)
  if (error) console.error('alerts fetch error:', error.message)
  return data ?? []
}

async function getHeartbeats(): Promise<Heartbeat[]> {
  const { data, error } = await getSupabase()
    .from('heartbeats')
    .select('*')
    .order('last_seen', { ascending: false })
  if (error) console.error('heartbeats fetch error:', error.message)
  return data ?? []
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

export default async function DashboardPage() {
  const [alerts, heartbeats] = await Promise.all([getAlerts(), getHeartbeats()])

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: '2rem 1rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '2rem' }}>
        ShopGuard
      </h1>

      {/* ── Store status ── */}
      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#94a3b8' }}>
          STORES
        </h2>
        {heartbeats.length === 0 ? (
          <p style={{ color: '#64748b' }}>No stores registered yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {heartbeats.map((hb) => {
              const online = isOnline(hb)
              return (
                <div
                  key={hb.store_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    background: '#1e2433',
                    borderRadius: 8,
                    padding: '0.75rem 1rem',
                  }}
                >
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: online ? '#22c55e' : '#ef4444',
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontWeight: 500 }}>{hb.store_id}</span>
                  <span style={{ color: '#64748b', fontSize: '0.875rem', marginLeft: 'auto' }}>
                    {online ? 'Online' : 'Offline'} — last seen {formatTime(hb.last_seen)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Alert feed ── */}
      <section>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#94a3b8' }}>
          RECENT ALERTS
        </h2>
        {alerts.length === 0 ? (
          <p style={{ color: '#64748b' }}>No alerts yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {alerts.map((alert) => (
              <div
                key={alert.id}
                style={{
                  background: '#1e2433',
                  borderRadius: 8,
                  padding: '1rem',
                  display: 'flex',
                  gap: '1rem',
                  alignItems: 'flex-start',
                }}
              >
                {alert.image_url && (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={alert.image_url}
                    alt="Alert frame"
                    style={{
                      width: 120,
                      height: 80,
                      objectFit: 'cover',
                      borderRadius: 6,
                      flexShrink: 0,
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span
                      style={{
                        background: '#7c3aed',
                        color: '#fff',
                        borderRadius: 4,
                        padding: '0 6px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                      }}
                    >
                      {alert.zone_name || 'unknown zone'}
                    </span>
                    <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                      cam {alert.camera_index}
                    </span>
                    <span style={{ color: '#64748b', fontSize: '0.75rem', marginLeft: 'auto' }}>
                      {formatTime(alert.created_at)}
                    </span>
                  </div>
                  <p style={{ margin: '0.4rem 0 0', fontSize: '0.875rem', color: '#94a3b8' }}>
                    store: {alert.store_id}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
