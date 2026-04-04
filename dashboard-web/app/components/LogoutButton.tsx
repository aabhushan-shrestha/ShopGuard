'use client'

import { createSupabaseBrowser } from '@/lib/supabase'
import { useRouter } from 'next/navigation'

export default function LogoutButton() {
  const router = useRouter()

  async function handleSignOut() {
    const supabase = createSupabaseBrowser()
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <button
      onClick={handleSignOut}
      style={{
        background: 'transparent',
        color: '#64748b',
        border: '1px solid #334155',
        borderRadius: 6,
        padding: '0.375rem 0.75rem',
        cursor: 'pointer',
        fontSize: '0.8rem',
      }}
    >
      Sign out
    </button>
  )
}
