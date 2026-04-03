import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseKey)

export interface Alert {
  id: string
  store_id: string
  camera_index: string
  zone_name: string
  timestamp: string
  image_url: string | null
  created_at: string
}

export interface Heartbeat {
  store_id: string
  last_seen: string
  created_at: string
}

/** Returns true if the store sent a heartbeat within the last 90 seconds. */
export function isOnline(heartbeat: Heartbeat | null): boolean {
  if (!heartbeat) return false
  const age = Date.now() - new Date(heartbeat.last_seen).getTime()
  return age < 90_000
}
