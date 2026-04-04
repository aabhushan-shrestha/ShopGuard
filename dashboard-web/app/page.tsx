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

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: '2rem 1rem' }}>
      {/* ── Header ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '2rem',
        }}
      >
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>ShopGuard</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ color: '#64748b', fontSize: '0.875rem' }}>{user.email}</span>
          <LogoutButton />
        </div>
      </div>

      {/* ── Store status ── */}
      <section style={{ marginBottom: '2rem' }}>
        <h2
          style={{
            fontSize: '1rem',
            fontWeight: 600,
            marginBottom: '0.75rem',
            color: '#94a3b8',
          }}
        >
          STORE STATUS
        </h2>
        <div
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
              background: heartbeat ? (online ? '#22c55e' : '#ef4444') : '#64748b',
              flexShrink: 0,
            }}
          />
          <span style={{ fontWeight: 500 }}>
            {heartbeat
              ? online
                ? 'Online'
                : 'Offline'
              : 'No agent connected yet'}
          </span>
          {heartbeat && (
            <span
              style={{
                color: '#64748b',
                fontSize: '0.875rem',
                marginLeft: 'auto',
              }}
            >
              last seen {formatTime(heartbeat.last_seen)}
            </span>
          )}
        </div>
      </section>

      {/* ── Alert feed ── */}
      <section>
        <h2
          style={{
            fontSize: '1rem',
            fontWeight: 600,
            marginBottom: '0.75rem',
            color: '#94a3b8',
          }}
        >
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
                  <div
                    style={{
                      display: 'flex',
                      gap: '0.5rem',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                    }}
                  >
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
                    <span
                      style={{
                        color: '#64748b',
                        fontSize: '0.75rem',
                        marginLeft: 'auto',
                      }}
                    >
                      {formatTime(alert.created_at)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
