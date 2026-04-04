import { createServerClient } from '@supabase/ssr'
import { createBrowserClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

/** Supabase client for use in Server Components and Route Handlers. */
export function createSupabaseServer() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Server Components cannot set cookies — middleware handles refresh
          }
        },
      },
    }
  )
}

/** Supabase client for use in Client Components (browser). */
export function createSupabaseBrowser() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}

export interface Alert {
  id: string
  user_id: string
  camera_index: string
  zone_name: string
  timestamp: string
  image_url: string | null
  created_at: string
}

export interface Heartbeat {
  user_id: string
  last_seen: string
  created_at: string
}

/** Returns true if the store sent a heartbeat within the last 90 seconds. */
export function isOnline(heartbeat: Heartbeat | null): boolean {
  if (!heartbeat) return false
  const age = Date.now() - new Date(heartbeat.last_seen).getTime()
  return age < 90_000
}
