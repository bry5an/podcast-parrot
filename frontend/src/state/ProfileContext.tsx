import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../lib/api';
import type { Profile } from '../lib/types';

const STORAGE_KEY = 'kotoba.profileId';

interface ProfileContextValue {
  profiles: Profile[];
  currentProfile: Profile | null;
  loading: boolean;
  selectProfile: (id: number) => void;
  clearProfile: () => void;
  refreshProfiles: () => Promise<Profile[]>;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [currentProfileId, setCurrentProfileId] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? Number(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  const refreshProfiles = useCallback(async () => {
    const list = await api.listProfiles();
    setProfiles(list);
    return list;
  }, []);

  useEffect(() => {
    refreshProfiles()
      .then((list) => {
        setCurrentProfileId((id) => {
          if (id != null && list.some((p) => p.id === id)) return id;
          // Only auto-select a profile that has actually been used before —
          // an untouched last_used_at means there's no real signal, so fall
          // through to the picker instead of guessing.
          const everUsed = list.filter((p): p is Profile & { last_used_at: string } => p.last_used_at != null);
          const lastUsed = [...everUsed].sort((a, b) => b.last_used_at.localeCompare(a.last_used_at))[0];
          if (!lastUsed) return null;
          localStorage.setItem(STORAGE_KEY, String(lastUsed.id));
          return lastUsed.id;
        });
      })
      .finally(() => setLoading(false));
    // refreshProfiles is stable (empty deps), so this still runs once on
    // mount only — re-running after an explicit clearProfile() would
    // immediately re-select the last-used profile and defeat the "Switch
    // profile" flow.
  }, [refreshProfiles]);

  const selectProfile = useCallback((id: number) => {
    localStorage.setItem(STORAGE_KEY, String(id));
    setCurrentProfileId(id);
    api.updateProfile(id, { last_used_at: new Date().toISOString() }).catch(() => {});
  }, []);

  const clearProfile = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setCurrentProfileId(null);
  }, []);

  const currentProfile = useMemo(
    () => profiles.find((p) => p.id === currentProfileId) ?? null,
    [profiles, currentProfileId],
  );

  return (
    <ProfileContext.Provider
      value={{ profiles, currentProfile, loading, selectProfile, clearProfile, refreshProfiles }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfiles() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfiles must be used within a ProfileProvider');
  return ctx;
}
